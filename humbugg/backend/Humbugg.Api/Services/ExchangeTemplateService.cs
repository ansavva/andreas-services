using Humbugg.Api.Data;
using Humbugg.Api.Models;

namespace Humbugg.Api.Services;

public interface IExchangeTemplateService
{
    Task<IReadOnlyList<ExchangeTemplate>> ListAsync(CancellationToken ct);
    Task<ExchangeTemplate> SaveAsync(SaveTemplateRequest request, CancellationToken ct);
    Task<ExchangeTemplate> UpdateAsync(string id, UpdateTemplateRequest request, CancellationToken ct);
    Task<ExchangeTemplate> DuplicateAsync(string id, CancellationToken ct);
    Task<GroupDetail> ApplyAsync(string id, ApplyTemplateRequest request, CancellationToken ct);
    Task DeleteAsync(string id, CancellationToken ct);
}
internal sealed class ExchangeTemplateService(
    ICurrentUser user, ITemplateRepository templates, IGroupRepository groups,
    IMembershipRepository members, IInvitationRepository invitationRows,
    IInvitationService invitations, IReminderService reminders, IPlanCatalog plans,
    IGroupService groupService) : IExchangeTemplateService
{
    public Task<IReadOnlyList<ExchangeTemplate>> ListAsync(CancellationToken ct) => templates.ListAsync(user.UserId, ct);

    public async Task<ExchangeTemplate> SaveAsync(SaveTemplateRequest request, CancellationToken ct)
    {
        var group = await Own(request.SourceGroupId, ct);
        plans.EnsureCapability(group.Plan, group.EntitlementId, PlanCapability.ExchangeTemplates);
        var reminder = (await reminders.GetAsync(group.GroupId, ct)).Settings;
        var memberships = await members.GetByGroupAsync(group.GroupId, ct);
        var accepted = (await invitationRows.GetByGroupAsync(group.GroupId, ct))
            .Where(x => !string.IsNullOrWhiteSpace(x.AcceptedUserId))
            .ToDictionary(x => x.AcceptedUserId!, x => x.Email, StringComparer.Ordinal);
        var candidates = memberships.Where(x => !x.IsOrganizer && accepted.ContainsKey(x.UserId))
            .Select(x => new TemplateParticipant(x.MemberId, x.DisplayName, accepted[x.UserId])).ToList();
        var now = DateTimeOffset.UtcNow.ToString("O");
        var value = new ExchangeTemplate(
            Guid.NewGuid().ToString(), Validation.Required(request.Name, "name", 100),
            group.Name, group.Description, DeadlineOffset(group.EventDate, group.SignupDeadline),
            "Share gift ideas, sizes, and useful preferences.", group.Exclusions.Count == 0 ? "none" : "preserve_existing",
            reminder, group.Customization ?? new(), candidates, group.GroupId, now, now);
        await templates.PutAsync(user.UserId, value, ct);
        return value;
    }

    public async Task<ExchangeTemplate> UpdateAsync(string id, UpdateTemplateRequest request, CancellationToken ct)
    {
        var old = await Get(id, ct);
        var customization = request.Customization is null ? old.Customization : CustomizationValidation.Validate(request.Customization);
        var policy = request.ExclusionsPolicy ?? old.ExclusionsPolicy;
        if (policy is not ("none" or "preserve_existing")) throw ApiException.BadRequest("exclusions_policy must be none or preserve_existing.");
        var value = old with
        {
            Name = Validation.Required(request.Name ?? old.Name, "name", 100),
            ExchangeName = Validation.Required(request.ExchangeName ?? old.ExchangeName, "exchange_name", 120),
            Description = Validation.Optional(request.Description ?? old.Description, 1000),
            SignupDeadlineDaysBeforeEvent = request.SignupDeadlineDaysBeforeEvent ?? old.SignupDeadlineDaysBeforeEvent,
            WishlistPrompt = Validation.Optional(request.WishlistPrompt ?? old.WishlistPrompt, 500),
            ExclusionsPolicy = policy,
            ReminderPreferences = request.ReminderPreferences ?? old.ReminderPreferences,
            Customization = customization,
            UpdatedAt = DateTimeOffset.UtcNow.ToString("O")
        };
        if (value.SignupDeadlineDaysBeforeEvent is < 0 or > 365) throw ApiException.BadRequest("Deadline offset must be between 0 and 365 days.");
        ValidateReminders(value.ReminderPreferences);
        await templates.PutAsync(user.UserId, value, ct);
        return value;
    }

    public async Task<ExchangeTemplate> DuplicateAsync(string id, CancellationToken ct)
    {
        var old = await Get(id, ct); var now = DateTimeOffset.UtcNow.ToString("O");
        var value = old with { TemplateId = Guid.NewGuid().ToString(), Name = $"{old.Name} copy", CreatedAt = now, UpdatedAt = now };
        await templates.PutAsync(user.UserId, value, ct); return value;
    }

    public async Task<GroupDetail> ApplyAsync(string id, ApplyTemplateRequest request, CancellationToken ct)
    {
        var template = await Get(id, ct); var group = await Own(request.TargetGroupId, ct);
        plans.EnsureCapability(group.Plan, group.EntitlementId, PlanCapability.ExchangeTemplates);
        plans.EnsureCapability(group.Plan, group.EntitlementId, PlanCapability.ExchangeCustomization);
        if (request.PriorMemberIds is null) throw ApiException.BadRequest("Confirm which prior participants, if any, should be invited.");
        var selected = request.PriorMemberIds.Distinct(StringComparer.Ordinal).ToList();
        var candidates = template.PriorParticipants.ToDictionary(x => x.MemberId, StringComparer.Ordinal);
        if (selected.Any(x => !candidates.ContainsKey(x))) throw ApiException.Forbidden("A selected participant is not part of this template.");
        var active = (await members.GetByGroupAsync(group.GroupId, ct)).Count(x => x.IsParticipating);
        var pending = (await invitationRows.GetByGroupAsync(group.GroupId, ct)).Count(x => x.Status == "sent");
        for (var i = 0; i < selected.Count; i++) plans.EnsureParticipantCapacity(group.Plan, group.EntitlementId, active + pending + i);

        var eventDate = DateOnly.TryParse(request.EventDate, out var parsed)
            ? parsed : throw ApiException.BadRequest("Choose the new event date.");
        var deadline = TemplateDates.Deadline(eventDate, template.SignupDeadlineDaysBeforeEvent).ToString("yyyy-MM-dd");
        await groupService.UpdateAsync(group.GroupId, new(template.ExchangeName, template.Description, eventDate.ToString("yyyy-MM-dd"), deadline, null), ct);
        var instructions = string.Join("\n\n", new[] { template.Customization.Instructions, template.WishlistPrompt }.Where(x => !string.IsNullOrWhiteSpace(x)));
        await groupService.UpdateCustomizationAsync(group.GroupId, new(template.Customization.Greeting, instructions, template.Customization.PrimaryColor, template.Customization.AccentColor, template.Customization.ImageDataUrl), ct);
        if (template.ExclusionsPolicy == "none") await groupService.SetExclusionsAsync(group.GroupId, new([]), ct);
        await reminders.UpdateAsync(group.GroupId, new(template.ReminderPreferences.State, template.ReminderPreferences.RemindUnacceptedInvitations, template.ReminderPreferences.RemindIncompleteReadiness, template.ReminderPreferences.IntervalDays, template.ReminderPreferences.QuietStartUtcHour, template.ReminderPreferences.QuietEndUtcHour), ct);
        if (selected.Count > 0) await invitations.CreateAsync(group.GroupId, new(selected.Select(x => candidates[x].Email).ToList()), ct);
        return await groupService.GetAsync(group.GroupId, ct);
    }

    public async Task DeleteAsync(string id, CancellationToken ct) { _ = await Get(id, ct); await templates.DeleteAsync(user.UserId, id, ct); }
    private async Task<ExchangeTemplate> Get(string id, CancellationToken ct) => await templates.GetAsync(user.UserId, id, ct) ?? throw ApiException.NotFound("Template not found.");
    private async Task<GroupRecord> Own(string? id, CancellationToken ct) { var g = string.IsNullOrWhiteSpace(id) ? null : await groups.GetAsync(id, ct); if (g is null) throw ApiException.NotFound("Exchange not found."); if (g.OwnerUserId != user.UserId) throw ApiException.Forbidden("Only the organizer can use templates."); return g; }
    private static int DeadlineOffset(string? eventDate, string? deadline) => DateOnly.TryParse(eventDate, out var e) && DateOnly.TryParse(deadline, out var d) ? Math.Max(0, e.DayNumber - d.DayNumber) : 0;
    private static void ValidateReminders(ReminderSettings value)
    {
        if (value.IntervalDays is < 1 or > 14) throw ApiException.BadRequest("Reminder interval must be between 1 and 14 days.");
        if (value.QuietStartUtcHour is < 0 or > 23 || value.QuietEndUtcHour is < 1 or > 24 || value.QuietStartUtcHour >= value.QuietEndUtcHour)
            throw ApiException.BadRequest("Quiet hours must define a valid UTC sending window.");
        if (value.State == ReminderState.Active && !value.RemindUnacceptedInvitations && !value.RemindIncompleteReadiness)
            throw ApiException.BadRequest("Enable at least one reminder rule before starting reminders.");
    }
}

internal static class TemplateDates
{
    internal static DateOnly Deadline(DateOnly eventDate, int daysBeforeEvent) => eventDate.AddDays(-daysBeforeEvent);
}
