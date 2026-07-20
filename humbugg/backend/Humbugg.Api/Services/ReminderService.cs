using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services.Email.Core;

namespace Humbugg.Api.Services;

public interface IReminderService
{
    Task<ReminderOverview> GetAsync(string groupId, CancellationToken cancellationToken = default);
    Task<ReminderOverview> UpdateAsync(string groupId, UpdateReminderSettingsRequest request, CancellationToken cancellationToken = default);
    Task<ReminderHistoryItem> SendManualAsync(string groupId, ManualReminderRequest request, CancellationToken cancellationToken = default);
}

internal interface IReminderProcessor
{
    Task ProcessDueAsync(DateTimeOffset now, CancellationToken cancellationToken = default);
}

internal sealed class ReminderService(
    ICurrentUser user,
    IGroupRepository groups,
    IMembershipRepository members,
    IInvitationRepository invitations,
    IReminderRepository reminders,
    IPlanCatalog plans,
    ITransactionalEmailTemplates templates,
    ITransactionalEmailService email,
    IAuditTrail audit,
    HumbuggSettings settings) : IReminderService, IReminderProcessor
{
    private static readonly TimeSpan ManualCooldown = TimeSpan.FromMinutes(15);

    public async Task<ReminderOverview> GetAsync(string groupId, CancellationToken cancellationToken = default)
    {
        await RequireOrganizerAsync(groupId, cancellationToken);
        return await OverviewAsync(groupId, cancellationToken);
    }

    public async Task<ReminderOverview> UpdateAsync(
        string groupId,
        UpdateReminderSettingsRequest request,
        CancellationToken cancellationToken = default)
    {
        await RequireOrganizerAsync(groupId, cancellationToken);
        if (request.IntervalDays is < 1 or > 14)
            throw ApiException.BadRequest("Reminder interval must be between 1 and 14 days.");
        if (request.QuietStartUtcHour is < 0 or > 23 || request.QuietEndUtcHour is < 1 or > 24 ||
            request.QuietStartUtcHour >= request.QuietEndUtcHour)
            throw ApiException.BadRequest("Quiet hours must define a valid UTC sending window.");
        if (request.State == ReminderState.Active &&
            !request.RemindUnacceptedInvitations &&
            !request.RemindIncompleteReadiness)
            throw ApiException.BadRequest("Enable at least one reminder rule before starting reminders.");

        var existing = await reminders.GetConfigurationAsync(groupId, cancellationToken);
        var now = DateTimeOffset.UtcNow;
        var next = request.State == ReminderState.Active
            ? ReminderSchedule.AlignToWindow(now.AddMinutes(5), request.QuietStartUtcHour, request.QuietEndUtcHour).ToString("O")
            : null;
        await reminders.SaveConfigurationAsync(new(
            groupId,
            request.State,
            request.RemindUnacceptedInvitations,
            request.RemindIncompleteReadiness,
            request.IntervalDays,
            request.QuietStartUtcHour,
            request.QuietEndUtcHour,
            next,
            existing?.LastManualAt,
            now.ToString("O")), cancellationToken);
        await audit.RecordAsync(
            AuditAction.ReminderConfigurationChanged,
            groupId,
            AuditTarget.Reminder(groupId),
            new Dictionary<string, string>
            {
                ["state"] = request.State.ToString().ToLowerInvariant(),
                ["interval_days"] = request.IntervalDays.ToString(System.Globalization.CultureInfo.InvariantCulture)
            },
            cancellationToken: cancellationToken);
        return await OverviewAsync(groupId, cancellationToken);
    }

    public async Task<ReminderHistoryItem> SendManualAsync(
        string groupId,
        ManualReminderRequest request,
        CancellationToken cancellationToken = default)
    {
        var group = await RequireOrganizerAsync(groupId, cancellationToken);
        var configuration = await reminders.GetConfigurationAsync(groupId, cancellationToken)
            ?? throw ApiException.Conflict("Configure reminders before sending one.");
        if (configuration.State == ReminderState.Stopped)
            throw ApiException.Conflict("Start or pause reminders before sending a manual reminder.");
        if (string.IsNullOrWhiteSpace(request.InvitationId))
            throw ApiException.BadRequest("invitation_id is required.");

        var invitation = await invitations.GetAsync(request.InvitationId, cancellationToken);
        if (invitation is null || invitation.GroupId != groupId)
            throw ApiException.NotFound("Invitation not found.");
        var eligibility = await ResolveReminderAsync(group, invitation, request.Rule, cancellationToken);

        var now = DateTimeOffset.UtcNow;
        if (!await reminders.ClaimManualRunAsync(
                groupId,
                now.Subtract(ManualCooldown).ToString("O"),
                now.ToString("O"),
                cancellationToken))
            throw ApiException.Conflict("Wait 15 minutes before sending another manual reminder.");

        var item = await SendAsync(
            group,
            invitation,
            request.Rule,
            $"manual:{now:O}",
            eligibility,
            cancellationToken);
        await audit.RecordAsync(
            AuditAction.ReminderSent,
            groupId,
            AuditTarget.Reminder(item.ReminderId),
            new Dictionary<string, string>
            {
                ["rule"] = request.Rule.ToString().ToLowerInvariant(),
                ["status"] = item.Status
            },
            cancellationToken: cancellationToken);
        return item;
    }

    public async Task ProcessDueAsync(DateTimeOffset now, CancellationToken cancellationToken = default)
    {
        foreach (var configuration in await reminders.GetDueAsync(now.ToString("O"), cancellationToken))
        {
            var due = DateTimeOffset.Parse(configuration.NextScheduledAt!);
            var next = ReminderSchedule.AlignToWindow(
                due.AddDays(configuration.IntervalDays),
                configuration.QuietStartUtcHour,
                configuration.QuietEndUtcHour);
            if (!await reminders.ClaimAutomaticRunAsync(
                    configuration.GroupId,
                    configuration.NextScheduledAt!,
                    next.ToString("O"),
                    cancellationToken))
                continue;
            if (!ReminderSchedule.IsWithinWindow(
                    now,
                    configuration.QuietStartUtcHour,
                    configuration.QuietEndUtcHour))
                continue;

            var group = await groups.GetAsync(configuration.GroupId, cancellationToken);
            if (group is null || group.Status != GroupStatus.Open) continue;
            var groupInvitations = await invitations.GetByGroupAsync(group.GroupId, cancellationToken);
            foreach (var invitation in groupInvitations)
            {
                if (configuration.RemindUnacceptedInvitations &&
                    IsBefore(group.SignupDeadline, now) &&
                    invitation.Status == "sent" &&
                    DateTimeOffset.Parse(invitation.ExpiresAt) > now)
                    await SendAutomaticAsync(group, invitation, ReminderRule.UnacceptedInvitation, due, cancellationToken);

                if (configuration.RemindIncompleteReadiness &&
                    IsBefore(group.EventDate, now) &&
                    invitation.Status == "accepted")
                    await SendAutomaticAsync(group, invitation, ReminderRule.IncompleteReadiness, due, cancellationToken);
            }
        }
    }

    private async Task SendAutomaticAsync(
        GroupRecord group,
        InvitationRecord invitation,
        ReminderRule rule,
        DateTimeOffset due,
        CancellationToken cancellationToken)
    {
        try
        {
            var item = await SendAsync(group, invitation, rule, $"automatic:{due:O}", cancellationToken);
            await audit.RecordAsync(
                AuditAction.ReminderSent,
                group.GroupId,
                AuditTarget.Reminder(item.ReminderId),
                new Dictionary<string, string>
                {
                    ["rule"] = rule.ToString().ToLowerInvariant(),
                    ["status"] = item.Status
                },
                cancellationToken: cancellationToken);
        }
        catch (ApiException error) when (error.StatusCode is 404 or 409)
        {
            // A recipient accepted, completed readiness, left, or was removed after the due
            // configuration was read. That recipient is no longer eligible and is safely skipped.
        }
    }

    private async Task<ReminderHistoryItem> SendAsync(
        GroupRecord group,
        InvitationRecord invitation,
        ReminderRule rule,
        string occurrence,
        CancellationToken cancellationToken)
    {
        var eligibility = await ResolveReminderAsync(group, invitation, rule, cancellationToken);
        return await SendAsync(group, invitation, rule, occurrence, eligibility, cancellationToken);
    }

    private async Task<ReminderHistoryItem> SendAsync(
        GroupRecord group,
        InvitationRecord invitation,
        ReminderRule rule,
        string occurrence,
        (string Reminder, string? RecipientUserId) eligibility,
        CancellationToken cancellationToken)
    {
        var (reminder, recipientUserId) = eligibility;
        var rendered = templates.Reminder(new(
            $"{group.GroupId}:{invitation.InvitationId}:{rule}:{occurrence}",
            invitation.Email,
            "there",
            group.Name,
            reminder,
            new Uri($"{settings.AppBaseUrl}/app/groups/{group.GroupId}"),
            recipientUserId));
        var result = await email.SendAsync(rendered, cancellationToken);
        var status = result.Suppressed ? "suppressed" : "sent";
        var history = new ReminderHistoryItem(
            rendered.MessageId,
            rule,
            invitation.InvitationId,
            status,
            DateTimeOffset.UtcNow.ToString("O"));
        try
        {
            await reminders.SaveHistoryAsync(group.GroupId, history, cancellationToken);
        }
        catch (ConditionalCheckFailedException)
        {
            // Stable message/history identifiers make scheduler retries idempotent.
        }
        return history;
    }

    private async Task<(string Reminder, string? RecipientUserId)> ResolveReminderAsync(
        GroupRecord group,
        InvitationRecord invitation,
        ReminderRule rule,
        CancellationToken cancellationToken)
    {
        if (rule == ReminderRule.UnacceptedInvitation)
        {
            if (invitation.Status != "sent" || DateTimeOffset.Parse(invitation.ExpiresAt) <= DateTimeOffset.UtcNow)
                throw ApiException.Conflict("This invitation no longer needs a reminder.");
            return ("Please accept your invitation and join the exchange.", null);
        }
        if (invitation.Status != "accepted" || string.IsNullOrWhiteSpace(invitation.AcceptedUserId))
            throw ApiException.Conflict("This participant has not accepted the invitation.");
        var membership = await members.GetByUserAndGroupAsync(
            invitation.AcceptedUserId,
            group.GroupId,
            cancellationToken);
        if (membership is null || !membership.IsParticipating)
            throw ApiException.NotFound("This participant is no longer active.");
        if (!string.IsNullOrWhiteSpace(membership.Wishlist))
            throw ApiException.Conflict("This participant is already ready.");
        return (
            "Please complete your wishlist so your giver can choose well.",
            invitation.AcceptedUserId);
    }

    private async Task<GroupRecord> RequireOrganizerAsync(string groupId, CancellationToken cancellationToken)
    {
        var group = await groups.GetAsync(groupId, cancellationToken)
            ?? throw ApiException.NotFound("Exchange not found.");
        if (group.OwnerUserId != user.UserId)
            throw ApiException.Forbidden("Only the organizer can manage reminders.");
        plans.EnsureCapability(group.Plan, group.EntitlementId, PlanCapability.AutomaticReminders);
        return group;
    }

    private async Task<ReminderOverview> OverviewAsync(string groupId, CancellationToken cancellationToken)
    {
        var configuration = await reminders.GetConfigurationAsync(groupId, cancellationToken)
            ?? new(groupId, ReminderState.Stopped, true, true, 3, 9, 20, null, null, DateTimeOffset.UtcNow.ToString("O"));
        return new(
            new(
                configuration.State,
                configuration.RemindUnacceptedInvitations,
                configuration.RemindIncompleteReadiness,
                configuration.IntervalDays,
                configuration.QuietStartUtcHour,
                configuration.QuietEndUtcHour),
            configuration.NextScheduledAt,
            await reminders.GetHistoryAsync(groupId, 20, cancellationToken));
    }

    private static bool IsBefore(string? date, DateTimeOffset now) =>
        string.IsNullOrWhiteSpace(date) ||
        !DateOnly.TryParse(date, out var parsed) ||
        parsed >= DateOnly.FromDateTime(now.UtcDateTime);
}

internal static class ReminderSchedule
{
    public static bool IsWithinWindow(DateTimeOffset value, int startHour, int endHour) =>
        value.UtcDateTime.Hour >= startHour && value.UtcDateTime.Hour < endHour;

    public static DateTimeOffset AlignToWindow(DateTimeOffset value, int startHour, int endHour)
    {
        var utc = value.ToUniversalTime();
        if (utc.Hour < startHour)
            return new DateTimeOffset(utc.Year, utc.Month, utc.Day, startHour, 0, 0, TimeSpan.Zero);
        if (utc.Hour >= endHour)
            return new DateTimeOffset(utc.Year, utc.Month, utc.Day, startHour, 0, 0, TimeSpan.Zero).AddDays(1);
        return utc;
    }
}
