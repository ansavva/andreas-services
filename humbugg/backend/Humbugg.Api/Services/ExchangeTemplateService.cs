using Humbugg.Api.Data;
using Humbugg.Api.Models;

namespace Humbugg.Api.Services;

public interface IExchangeTemplateService
{
    Task<IReadOnlyList<ExchangeTemplate>> ListAsync(CancellationToken ct); Task<ExchangeTemplate> SaveAsync(SaveTemplateRequest request, CancellationToken ct); Task<ExchangeTemplate> RenameAsync(string id, SaveTemplateRequest request, CancellationToken ct); Task<ExchangeTemplate> DuplicateAsync(string id, CancellationToken ct); Task<GroupDetail> ApplyAsync(string id, ApplyTemplateRequest request, CancellationToken ct); Task DeleteAsync(string id, CancellationToken ct);
}
internal sealed class ExchangeTemplateService(ICurrentUser user, ITemplateRepository templates, IGroupRepository groups, IMembershipRepository members, IPlanCatalog plans, IGroupService groupService) : IExchangeTemplateService
{
    public Task<IReadOnlyList<ExchangeTemplate>> ListAsync(CancellationToken ct) => templates.ListAsync(user.UserId, ct);
    public async Task<ExchangeTemplate> SaveAsync(SaveTemplateRequest r, CancellationToken ct) { var g = await Own(r.SourceGroupId, ct); plans.EnsureCapability(g.Plan, g.EntitlementId, PlanCapability.ExchangeTemplates); var now = DateTimeOffset.UtcNow.ToString("O"); var t = new ExchangeTemplate(Guid.NewGuid().ToString(), Validation.Required(r.Name, "name", 100), g.Name, g.Description, Offset(g.EventDate), Offset(g.SignupDeadline), "Share gift ideas and sizes.", "Organizer-defined pairs", true, g.Customization ?? new(), g.GroupId, now, now); await templates.PutAsync(user.UserId, t, ct); return t; }
    public async Task<ExchangeTemplate> RenameAsync(string id, SaveTemplateRequest r, CancellationToken ct) { var t = await Get(id, ct); var n = t with { Name = Validation.Required(r.Name, "name", 100), UpdatedAt = DateTimeOffset.UtcNow.ToString("O") }; await templates.PutAsync(user.UserId, n, ct); return n; }
    public async Task<ExchangeTemplate> DuplicateAsync(string id, CancellationToken ct) { var t = await Get(id, ct); var now = DateTimeOffset.UtcNow.ToString("O"); var n = t with { TemplateId = Guid.NewGuid().ToString(), Name = $"{t.Name} copy", CreatedAt = now, UpdatedAt = now }; await templates.PutAsync(user.UserId, n, ct); return n; }
    public async Task<GroupDetail> ApplyAsync(string id, ApplyTemplateRequest r, CancellationToken ct) { var t = await Get(id, ct); var g = await Own(r.TargetGroupId, ct); plans.EnsureCapability(g.Plan, g.EntitlementId, PlanCapability.ExchangeTemplates); plans.EnsureCapability(g.Plan, g.EntitlementId, PlanCapability.ExchangeCustomization); if (r.PriorMemberIds is null) throw ApiException.BadRequest("Confirm which prior participants, if any, should be invited."); var allowed = t.SourceGroupId is null ? new HashSet<string>() : (await members.GetByGroupAsync(t.SourceGroupId, ct)).Select(x => x.MemberId).ToHashSet(); if (r.PriorMemberIds.Any(x => !allowed.Contains(x))) throw ApiException.Forbidden("A selected participant did not belong to the source exchange."); await groupService.UpdateAsync(g.GroupId, new(t.ExchangeName, t.Description, Date(r.EventDate, t.EventDateOffsetDays), Date(r.EventDate, t.SignupDeadlineOffsetDays), null), ct); return await groupService.UpdateCustomizationAsync(g.GroupId, new(t.Customization.Greeting, t.Customization.Instructions, t.Customization.PrimaryColor, t.Customization.AccentColor, t.Customization.ImageDataUrl), ct); }
    public Task DeleteAsync(string id, CancellationToken ct) => templates.DeleteAsync(user.UserId, id, ct);
    private async Task<ExchangeTemplate> Get(string id, CancellationToken ct) => await templates.GetAsync(user.UserId, id, ct) ?? throw ApiException.NotFound("Template not found.");
    private async Task<GroupRecord> Own(string? id, CancellationToken ct) { var g = string.IsNullOrWhiteSpace(id) ? null : await groups.GetAsync(id, ct); if (g is null) throw ApiException.NotFound("Exchange not found."); if (g.OwnerUserId != user.UserId) throw ApiException.Forbidden("Only the organizer can use templates."); return g; }
    private static int Offset(string? d) => DateOnly.TryParse(d, out var x) ? Math.Max(0, x.DayNumber - DateOnly.FromDateTime(DateTime.UtcNow).DayNumber) : 0;
    private static string? Date(string? basis, int offset) => DateOnly.TryParse(basis, out var x) ? x.AddDays(offset).ToString("yyyy-MM-dd") : null;
}
