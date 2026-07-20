using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services.Email.Core;

namespace Humbugg.Api.Services;

public interface ILateParticipantService
{
    Task<LateParticipantPreview> PreviewAsync(string groupId, string memberId, CancellationToken cancellationToken = default);
    Task<LateParticipantResult> ConfirmAsync(string groupId, ConfirmLateParticipantRequest request, CancellationToken cancellationToken = default);
}

internal sealed class LateParticipantService(
    ICurrentUser user,
    IGroupRepository groups,
    IMembershipRepository members,
    IInvitationRepository invitations,
    IMatchingService matching,
    IPlanCatalog plans,
    ITransactionalEmailTemplates templates,
    ITransactionalEmailService email,
    IAuditTrail audit,
    HumbuggSettings settings) : ILateParticipantService
{
    private static readonly TimeSpan ProposalLifetime = TimeSpan.FromMinutes(15);

    public async Task<LateParticipantPreview> PreviewAsync(
        string groupId,
        string memberId,
        CancellationToken cancellationToken = default)
    {
        var group = await RequireManagerAsync(groupId, cancellationToken);
        if (group.Status != GroupStatus.Drawn)
            throw ApiException.Conflict("Create the draw before previewing a late participant.");
        var member = await RequirePendingMemberAsync(groupId, memberId, cancellationToken);
        var roster = await members.GetByGroupAsync(groupId, cancellationToken);
        plans.EnsureParticipantCapacity(
            group.Plan,
            group.EntitlementId,
            roster.Count(item => item.IsParticipating));
        await audit.RecordAsync(
            AuditAction.LateParticipantRequested,
            groupId,
            AuditTarget.Member(memberId),
            cancellationToken: cancellationToken);

        var draw = await groups.GetDrawAsync(groupId, cancellationToken)
            ?? throw ApiException.NotFound("Draw record not found.");
        var result = matching.CreateMinimalChangeAssignments(
            draw.Assignments,
            member.MemberId,
            group.Exclusions);
        await ResolveNotificationTargetsAsync(group, result.AffectedMemberIds, cancellationToken);
        var proposalId = Guid.NewGuid().ToString("N");
        var expires = DateTimeOffset.UtcNow.Add(ProposalLifetime).ToString("O");
        var proposal = new LateParticipantProposalRecord(
            proposalId,
            member.MemberId,
            draw.DrawId,
            result.Assignments,
            result.AffectedMemberIds,
            expires);
        try
        {
            await groups.SaveLateProposalAsync(groupId, draw.DrawId, proposal, cancellationToken);
        }
        catch (ConditionalCheckFailedException)
        {
            throw ApiException.Conflict("The draw changed while the late-participant impact was calculated. Preview it again.");
        }
        return new(proposalId, member.MemberId, result.AffectedMemberIds.Count, expires);
    }

    public async Task<LateParticipantResult> ConfirmAsync(
        string groupId,
        ConfirmLateParticipantRequest request,
        CancellationToken cancellationToken = default)
    {
        var group = await RequireManagerAsync(groupId, cancellationToken);
        if (!request.Confirm || string.IsNullOrWhiteSpace(request.ProposalId))
            throw ApiException.BadRequest("Explicit confirmation and proposal_id are required.");
        var draw = await groups.GetDrawAsync(groupId, cancellationToken)
            ?? throw ApiException.NotFound("Draw record not found.");

        if (draw.LateProposal is null)
        {
            if (draw.LastLateProposalId == request.ProposalId &&
                draw.LastLateMemberId is not null &&
                draw.LastAffectedMemberIds is not null)
            {
                var retryTargets = await ResolveNotificationTargetsAsync(
                    group,
                    draw.LastAffectedMemberIds,
                    cancellationToken);
                await NotifyAffectedAsync(
                    group,
                    request.ProposalId,
                    draw.DrawId,
                    retryTargets,
                    cancellationToken);
                return new(draw.LastLateMemberId, draw.LastAffectedMemberIds.Count, draw.DrawId);
            }
            throw ApiException.Conflict("This late-participant preview is stale. Create a new preview.");
        }

        var proposal = draw.LateProposal;
        if (proposal.ProposalId != request.ProposalId ||
            proposal.ExpectedDrawId != draw.DrawId ||
            DateTimeOffset.Parse(proposal.ExpiresAt) <= DateTimeOffset.UtcNow)
            throw ApiException.Conflict("This late-participant preview is stale or expired. Create a new preview.");
        await RequirePendingMemberAsync(groupId, proposal.MemberId, cancellationToken);
        var notificationTargets = await ResolveNotificationTargetsAsync(
            group,
            proposal.AffectedMemberIds,
            cancellationToken);

        string newDrawId;
        try
        {
            newDrawId = await groups.ApplyLateProposalAsync(
                groupId,
                draw.DrawId,
                proposal,
                cancellationToken);
        }
        catch (TransactionCanceledException)
        {
            throw ApiException.Conflict("The draw or participant changed before confirmation. Create a new preview.");
        }
        await audit.RecordAsync(
            AuditAction.LateParticipantConfirmed,
            groupId,
            AuditTarget.Member(proposal.MemberId),
            new Dictionary<string, string>
            {
                ["affected_count"] = proposal.AffectedMemberIds.Count.ToString(System.Globalization.CultureInfo.InvariantCulture)
            },
            cancellationToken: cancellationToken);
        await audit.RecordAsync(
            AuditAction.LateAssignmentsChanged,
            groupId,
            AuditTarget.Draw(groupId),
            new Dictionary<string, string>
            {
                ["affected_count"] = proposal.AffectedMemberIds.Count.ToString(System.Globalization.CultureInfo.InvariantCulture),
                ["draw_version"] = newDrawId
            },
            cancellationToken: cancellationToken);
        await NotifyAffectedAsync(
            group,
            proposal.ProposalId,
            newDrawId,
            notificationTargets,
            cancellationToken);
        return new(proposal.MemberId, proposal.AffectedMemberIds.Count, newDrawId);
    }

    private async Task NotifyAffectedAsync(
        GroupRecord group,
        string proposalId,
        string drawVersion,
        IReadOnlyDictionary<string, NotificationTarget> targets,
        CancellationToken cancellationToken)
    {
        foreach (var (memberId, target) in targets)
        {
            var message = templates.AssignmentAvailable(new(
                $"late:{proposalId}:{memberId}",
                target.Email,
                target.DisplayName,
                group.Name,
                new Uri($"{settings.AppBaseUrl}/app/groups/{group.GroupId}?assignment_version={Uri.EscapeDataString(drawVersion)}")));
            await email.SendAsync(message, cancellationToken);
        }
    }

    private async Task<IReadOnlyDictionary<string, NotificationTarget>> ResolveNotificationTargetsAsync(
        GroupRecord group,
        IReadOnlyList<string> affectedMemberIds,
        CancellationToken cancellationToken)
    {
        var roster = (await members.GetByGroupAsync(group.GroupId, cancellationToken))
            .ToDictionary(item => item.MemberId, StringComparer.Ordinal);
        var contacts = await ContactsAsync(group.GroupId, cancellationToken);
        if (!string.IsNullOrWhiteSpace(user.Email))
            contacts[user.UserId] = user.Email;
        var targets = new Dictionary<string, NotificationTarget>(StringComparer.Ordinal);
        foreach (var memberId in affectedMemberIds)
        {
            if (!roster.TryGetValue(memberId, out var member))
                throw ApiException.Conflict("An affected participant is no longer in this exchange. Preview the change again.");
            if (!contacts.TryGetValue(member.UserId, out var address))
                throw ApiException.Conflict(
                    "Every affected participant must have a verified notification address before the draw can change.");
            targets[memberId] = new(member.DisplayName, address);
        }
        return targets;
    }

    private async Task<Dictionary<string, string>> ContactsAsync(
        string groupId,
        CancellationToken cancellationToken) =>
        (await invitations.GetByGroupAsync(groupId, cancellationToken))
            .Where(item => item.Status == "accepted" && !string.IsNullOrWhiteSpace(item.AcceptedUserId))
            .GroupBy(item => item.AcceptedUserId!, StringComparer.Ordinal)
            .ToDictionary(group => group.Key, group => group.OrderByDescending(item => item.AcceptedAt, StringComparer.Ordinal).First().Email, StringComparer.Ordinal);

    private sealed record NotificationTarget(string DisplayName, string Email);

    private async Task<GroupRecord> RequireManagerAsync(string groupId, CancellationToken cancellationToken)
    {
        var group = await groups.GetAsync(groupId, cancellationToken)
            ?? throw ApiException.NotFound("Exchange not found.");
        var membership = await members.GetByUserAndGroupAsync(user.UserId, groupId, cancellationToken);
        if (membership?.IsOrganizer != true)
            throw ApiException.Forbidden("Only an organizer can add a late participant.");
        plans.EnsureCapability(group.Plan, group.EntitlementId, PlanCapability.LateParticipants);
        return group;
    }

    private async Task<MembershipRecord> RequirePendingMemberAsync(
        string groupId,
        string memberId,
        CancellationToken cancellationToken)
    {
        var member = await members.GetAsync(memberId, cancellationToken);
        if (member is null || member.GroupId != groupId)
            throw ApiException.NotFound("Late participant not found.");
        if (member.IsParticipating)
            throw ApiException.Conflict("This participant is already included in the draw.");
        return member;
    }
}
