using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Microsoft.AspNetCore.WebUtilities;
using System.Security.Cryptography;
using System.Text;

namespace Humbugg.Api.Services;

public interface IGroupService
{
    Task<IReadOnlyList<GroupSummary>> ListAsync(CancellationToken cancellationToken = default);
    Task<GroupDetail> CreateAsync(CreateGroupRequest request, CancellationToken cancellationToken = default);
    Task<GroupDetail> GetAsync(string groupId, CancellationToken cancellationToken = default);
    Task<GroupReadiness> GetReadinessAsync(string groupId, CancellationToken cancellationToken = default);
    Task<GroupDetail> UpdateAsync(string groupId, UpdateGroupRequest request, CancellationToken cancellationToken = default);
    Task<GroupDetail> UpdateCustomizationAsync(string groupId, UpdateCustomizationRequest request, CancellationToken cancellationToken = default);
    Task<InvitationPreview> GetInvitationAsync(string groupId, string? inviteToken, CancellationToken cancellationToken = default);
    Task DeleteAsync(string groupId, CancellationToken cancellationToken = default);
    Task<InviteResponse> RotateInviteAsync(string groupId, CancellationToken cancellationToken = default);
    Task<GroupDetail> JoinAsync(string groupId, JoinGroupRequest request, CancellationToken cancellationToken = default);
    Task<Membership> GetMyMembershipAsync(string groupId, CancellationToken cancellationToken = default);
    Task<Membership> UpdateMyMembershipAsync(string groupId, UpdateMembershipRequest request, CancellationToken cancellationToken = default);
    Task<Membership> ClearMyPrivateDataAsync(string groupId, CancellationToken cancellationToken = default);
    Task LeaveAsync(string groupId, CancellationToken cancellationToken = default);
    Task<Membership> UpdateParticipationAsync(string groupId, string memberId, ParticipationRequest request, CancellationToken cancellationToken = default);
    Task<Membership> UpdateOrganizerRoleAsync(string groupId, string memberId, OrganizerRoleRequest request, CancellationToken cancellationToken = default);
    Task<GroupDetail> SetExclusionsAsync(string groupId, ExclusionsRequest request, CancellationToken cancellationToken = default);
    Task<RecipientAssignment> DrawAsync(string groupId, CancellationToken cancellationToken = default);
    Task<GroupDetail> ResetAsync(string groupId, CancellationToken cancellationToken = default);
    Task<RecipientAssignment> GetAssignmentAsync(string groupId, CancellationToken cancellationToken = default);
    Task<RecipientAssignment> GetAssignmentAsync(string groupId, string? drawVersion, CancellationToken cancellationToken = default);
    Task<RevealResponse> RevealAsync(string groupId, RevealRequest request, CancellationToken cancellationToken = default);
}

internal sealed class GroupService(
    ICurrentUser user,
    IProfileRepository profiles,
    IGroupRepository groups,
    IMembershipRepository memberships,
    IWishRepository wishes,
    IInvitationRepository invitations,
    IMatchingService matching,
    IPlanCatalog plans,
    IAuditTrail audit,
    IProductAnalytics analytics,
    HumbuggSettings settings) : IGroupService
{
    public async Task<IReadOnlyList<GroupSummary>> ListAsync(CancellationToken cancellationToken = default)
    {
        var result = new List<GroupSummary>();
        foreach (var membership in await memberships.GetByUserAsync(user.UserId, cancellationToken))
        {
            var group = await groups.GetAsync(membership.GroupId, cancellationToken);
            if (group is not null) result.Add(Summary(group, membership));
        }
        return result.OrderByDescending(item => item.CreatedAt, StringComparer.Ordinal).ToList();
    }

    public async Task<GroupDetail> CreateAsync(CreateGroupRequest request, CancellationToken cancellationToken = default)
    {
        var profile = await profiles.GetAsync(user.UserId, cancellationToken)
            ?? throw ApiException.Conflict("Complete your profile before creating a group.");
        var isRepeatOrganizer = (await memberships.GetByUserAsync(user.UserId, cancellationToken)).Any(item => item.IsOrganizer);
        var secret = NewSecret();
        var now = DateTimeOffset.UtcNow.ToString("O");
        var dates = Validation.GroupDates(request.EventDate, request.SignupDeadline);
        var group = new GroupRecord(
            Guid.NewGuid().ToString(), user.UserId, Validation.Required(request.Name, "name", 120),
            Validation.Optional(request.Description, 1000), dates.EventDate,
            dates.SignupDeadline, Validation.SpendingLimit(request.SpendingLimit),
            "USD", PlanCode.Free, null, GroupStatus.Open, Hash(secret), [], now, now);
        await groups.CreateAsync(group, cancellationToken);
        await memberships.CreateAsync(group.GroupId, user.UserId, profile.DisplayName, true, cancellationToken);
        await audit.RecordAsync(AuditAction.GroupCreated, group.GroupId, AuditTarget.Group(group.GroupId),
            new Dictionary<string, string> { ["plan"] = group.Plan.ToString().ToLowerInvariant() }, cancellationToken: cancellationToken);
        await analytics.TrackAsync(AnalyticsEventType.GroupCreated, group.Plan, group.GroupId,
            $"group_created:{group.GroupId}",
            new Dictionary<string, string> { ["is_repeat"] = isRepeatOrganizer ? "true" : "false" }, cancellationToken);
        if (isRepeatOrganizer)
            await analytics.TrackAsync(AnalyticsEventType.RepeatExchangeCreated, group.Plan, group.GroupId,
                $"repeat_exchange:{group.GroupId}", cancellationToken: cancellationToken);
        // The first invite is created with the group; count it once so invite-to-join has a denominator.
        await analytics.TrackAsync(AnalyticsEventType.InviteSent, group.Plan, group.GroupId,
            $"invite_sent:{group.GroupId}", cancellationToken: cancellationToken);
        var detail = await GetAsync(group.GroupId, cancellationToken);
        return detail with { InviteUrl = InviteUrl(group.GroupId, secret) };
    }

    public async Task<GroupDetail> GetAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var (group, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        var members = await memberships.GetByGroupAsync(groupId, cancellationToken);
        return Detail(group, membership, members);
    }

    /// <summary>
    /// The organizer readiness dashboard (#133): who has joined, who has done what, and who needs a
    /// nudge. Organizer-only, and never gated on a plan — a Free exchange needs to know its roster is
    /// ready as much as a Plus one does, and the tiers differ only in what the answer contains.
    ///
    /// Nothing a participant wrote is in this response. Readiness is a state and a count, never a
    /// wish, an address or an assignment: the organizer learns that someone's list is empty, not
    /// what is on it, and learns that someone has opened their assignment, not whose name was in it.
    /// </summary>
    public async Task<GroupReadiness> GetReadinessAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var (group, actor) = await RequireMembershipAsync(groupId, cancellationToken);
        RequireOrganizer(actor);
        var members = await memberships.GetByGroupAsync(groupId, cancellationToken);
        var draw = group.Status == GroupStatus.Drawn
            ? await groups.GetDrawAsync(groupId, cancellationToken)
            : null;
        var wishCounts = await WishCountsAsync(members.Where(item => item.IsParticipating), cancellationToken);

        var participants = members
            .Select(member => Readiness(member, group, draw, wishCounts.GetValueOrDefault(member.MemberId)))
            .OrderBy(item => item.DisplayName, StringComparer.CurrentCultureIgnoreCase)
            .ThenBy(item => item.MemberId, StringComparer.Ordinal)
            .ToList();
        var pending = await PendingInvitationsAsync(groupId, cancellationToken);
        var participating = participants.Where(item => item.IsParticipating).ToList();

        var counts = new ReadinessCounts(
            Members: participants.Count,
            Participating: participating.Count,
            NotParticipating: participants.Count - participating.Count,
            PendingInvitations: pending.Count,
            WishlistReady: participating.Count(item => item.Wishlist == ReadinessState.Ready),
            AddressReady: participating.Count(item => item.Address == ReadinessState.Ready),
            AssignmentsViewed: participating.Count(item => item.Assignment == ReadinessState.Ready),
            NeedsNudge: participating.Count(item => item.Nudges.Count > 0) + pending.Count);

        return new GroupReadiness(
            group.GroupId, group.Status, group.Plan, group.RequiresAddress, counts, participants, pending,
            // #132 owns purchased / sent / received. Until it lands there is nothing to aggregate, and
            // null says exactly that — see GiftProgress on why this is not three zeroes.
            GiftProgress: null);
    }

    private static ParticipantReadiness Readiness(MembershipRecord member, GroupRecord group, DrawRecord? draw, int wishCount)
    {
        var hasPreferences = !string.IsNullOrWhiteSpace(member.Wishlist);
        // Ready on either the structured list (#127) or the free-text preferences, because both are a
        // real answer to "what would you like". The free-text field was never replaced by wishes, so
        // counting only wishes would report a list written before wishes existed as missing.
        var wishlist = !member.IsParticipating ? ReadinessState.NotApplicable
            : wishCount > 0 || hasPreferences ? ReadinessState.Ready
            : ReadinessState.Missing;
        var address = !member.IsParticipating ? ReadinessState.NotApplicable
            : !group.RequiresAddress ? ReadinessState.NotRequired
            : HasAddress(member.Address) ? ReadinessState.Ready
            : ReadinessState.Missing;
        var assignment = !member.IsParticipating || draw is null ? ReadinessState.NotApplicable
            : member.AssignmentViewedDrawId == draw.DrawId ? ReadinessState.Ready
            : ReadinessState.Missing;

        var nudges = new List<NudgeReason>();
        if (wishlist == ReadinessState.Missing) nudges.Add(NudgeReason.NoWishlist);
        if (address == ReadinessState.Missing) nudges.Add(NudgeReason.NoAddress);
        if (assignment == ReadinessState.Missing) nudges.Add(NudgeReason.AssignmentNotViewed);

        return new ParticipantReadiness(
            member.MemberId,
            member.DisplayName,
            member.UserId == group.OwnerUserId ? ParticipantRole.Owner
                : member.IsOrganizer ? ParticipantRole.CoOrganizer
                : ParticipantRole.Participant,
            member.IsParticipating,
            wishlist,
            wishCount,
            hasPreferences,
            address,
            assignment,
            nudges);
    }

    private async Task<IReadOnlyList<PendingInvitation>> PendingInvitationsAsync(string groupId, CancellationToken cancellationToken)
    {
        var result = new List<PendingInvitation>();
        foreach (var row in await invitations.GetByGroupAsync(groupId, cancellationToken))
        {
            // Only rows that could still be pending pay for a delivery-status lookup; an accepted or
            // revoked invitation is settled by its own column and never reaches the dashboard.
            if (row.Status is "accepted" or "revoked") continue;
            var status = InvitationStatusRule.Of(row, await invitations.GetDeliveryStatusAsync(row.MessageId, cancellationToken));
            if (InvitationStatusRule.IsPending(status))
                result.Add(new PendingInvitation(row.InvitationId, row.Email, status, row.ExpiresAt, row.LastSentAt));
        }
        return result.OrderBy(item => item.Email, StringComparer.OrdinalIgnoreCase).ToList();
    }

    // One Query per participant. The wishes table has no group index on purpose — member_id is the
    // partition key precisely so no wish can be addressed without naming its owner (see
    // infra/modules/storage) — so a group roll-up is N queries, run ten at a time. That is nothing at
    // the Free limit of 6 or the Plus limit of 50. It would be far too much at Work's 10,000, which
    // is a reason Work needs a stored aggregate before it ships, not a reason to index wish content.
    private async Task<IReadOnlyDictionary<string, int>> WishCountsAsync(
        IEnumerable<MembershipRecord> members,
        CancellationToken cancellationToken)
    {
        var counts = new Dictionary<string, int>(StringComparer.Ordinal);
        foreach (var batch in members.Chunk(10))
        {
            foreach (var result in await Task.WhenAll(batch.Select(async member =>
                (member.MemberId, Count: (await wishes.GetByMemberAsync(member.MemberId, cancellationToken)).Count))))
                counts[result.MemberId] = result.Count;
        }
        return counts;
    }

    /// <summary>A stored address is all-or-nothing: Validation.Address rejects a partial one, so
    /// line1 alone is enough to know the rest is there. Checked in full anyway — this reads a row,
    /// and a readiness answer should not depend on a rule enforced somewhere else.</summary>
    private static bool HasAddress(Address address) =>
        !string.IsNullOrWhiteSpace(address.Line1) && !string.IsNullOrWhiteSpace(address.City) &&
        !string.IsNullOrWhiteSpace(address.PostalCode) && !string.IsNullOrWhiteSpace(address.Country);

    public async Task<GroupDetail> UpdateAsync(string groupId, UpdateGroupRequest request, CancellationToken cancellationToken = default)
    {
        var (group, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        RequireOrganizer(membership);
        var fields = new Dictionary<string, AttributeValue>();
        if (request.Name is not null) fields["name"] = DynamoValues.S(Validation.Required(request.Name, "name", 120));
        if (request.Description is not null) fields["description"] = DynamoValues.S(Validation.Optional(request.Description, 1000));
        if (request.EventDate is not null || request.SignupDeadline is not null)
        {
            var dates = Validation.GroupDates(request.EventDate ?? group.EventDate, request.SignupDeadline ?? group.SignupDeadline);
            if (request.EventDate is not null) fields["event_date"] = DynamoValues.S(dates.EventDate ?? "");
            if (request.SignupDeadline is not null) fields["signup_deadline"] = DynamoValues.S(dates.SignupDeadline ?? "");
        }
        if (request.SpendingLimit is not null) fields["spending_limit_cents"] = DynamoValues.N(Validation.SpendingLimit(request.SpendingLimit)!.Value);
        // Allowed after the draw as well as before it. Turning it on late is exactly what an
        // organizer does when the plan changes from "we'll swap at the party" to "post them".
        if (request.RequiresAddress is not null) fields["requires_address"] = DynamoValues.B(request.RequiresAddress.Value);
        if (fields.Count > 0)
        {
            await groups.UpdateAsync(groupId, fields, cancellationToken: cancellationToken);
            await audit.RecordAsync(AuditAction.GroupUpdated, groupId, AuditTarget.Group(groupId),
                new Dictionary<string, string> { ["fields"] = string.Join(",", fields.Keys.Order(StringComparer.Ordinal)) }, cancellationToken: cancellationToken);
        }
        return await GetAsync(groupId, cancellationToken);
    }

    public async Task<GroupDetail> UpdateCustomizationAsync(string groupId, UpdateCustomizationRequest request, CancellationToken cancellationToken = default)
    {
        var (group, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        RequireOrganizer(membership);
        plans.EnsureCapability(group.Plan, group.EntitlementId, PlanCapability.ExchangeCustomization);
        var customization = CustomizationValidation.Validate(request);
        await groups.UpdateAsync(groupId, new Dictionary<string, AttributeValue>
        {
            ["customization"] = new()
            {
                M = new()
                {
                    ["greeting"] = DynamoValues.S(customization.Greeting),
                    ["instructions"] = DynamoValues.S(customization.Instructions),
                    ["primary_color"] = DynamoValues.S(customization.PrimaryColor),
                    ["accent_color"] = DynamoValues.S(customization.AccentColor),
                    ["image"] = DynamoValues.S(customization.ImageDataUrl ?? "")
                }
            }
        }, cancellationToken: cancellationToken);
        return await GetAsync(groupId, cancellationToken);
    }

    public async Task<InvitationPreview> GetInvitationAsync(string groupId, string? inviteToken, CancellationToken cancellationToken = default)
    {
        var group = await RequireGroupAsync(groupId, cancellationToken);
        var token = Validation.InviteToken(inviteToken);
        if (token is null || !CryptographicOperations.FixedTimeEquals(
            Encoding.UTF8.GetBytes(Hash(token)), Encoding.UTF8.GetBytes(group.InviteHash)))
            throw ApiException.Forbidden("This invitation is invalid or has expired.");
        return new(group.GroupId, group.Name, group.Customization ?? new ExchangeCustomization());
    }

    public async Task DeleteAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var (group, _) = await RequireMembershipAsync(groupId, cancellationToken);
        RequireOwner(group);
        await memberships.DeleteByGroupAsync(groupId, cancellationToken);
        await groups.DeleteAsync(groupId, cancellationToken);
        await audit.RecordAsync(AuditAction.GroupDeleted, groupId, AuditTarget.Group(groupId), cancellationToken: cancellationToken);
    }

    public async Task<InviteResponse> RotateInviteAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var (group, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        RequireOrganizer(membership); RequireOpen(group);
        var secret = NewSecret();
        await ConditionalGroupUpdate(() => groups.UpdateAsync(groupId,
            new Dictionary<string, AttributeValue> { ["invite_hash"] = DynamoValues.S(Hash(secret)) }, GroupStatus.Open, cancellationToken));
        await audit.RecordAsync(AuditAction.InviteRotated, groupId, AuditTarget.Invite(groupId), cancellationToken: cancellationToken);
        // Deduped per group: a group has "an invite" whether it was rotated once or many times.
        await analytics.TrackAsync(AnalyticsEventType.InviteSent, group.Plan, groupId,
            $"invite_sent:{groupId}", cancellationToken: cancellationToken);
        return new InviteResponse(InviteUrl(groupId, secret));
    }

    public async Task<GroupDetail> JoinAsync(string groupId, JoinGroupRequest request, CancellationToken cancellationToken = default)
    {
        var group = await RequireGroupAsync(groupId, cancellationToken); RequireOpen(group);
        if (await memberships.GetByUserAndGroupAsync(user.UserId, groupId, cancellationToken) is not null)
            return await GetAsync(groupId, cancellationToken);
        var profile = await profiles.GetAsync(user.UserId, cancellationToken)
            ?? throw ApiException.Conflict("Complete your profile before joining a group.");
        var inviteToken = Validation.InviteToken(request.InviteToken);
        if (inviteToken is null || !CryptographicOperations.FixedTimeEquals(
                Encoding.UTF8.GetBytes(Hash(inviteToken)), Encoding.UTF8.GetBytes(group.InviteHash)))
            throw ApiException.Forbidden("This invitation is invalid or has expired.");
        var currentMembers = await memberships.GetByGroupAsync(groupId, cancellationToken);
        plans.EnsureParticipantCapacity(
            group.Plan, group.EntitlementId, currentMembers.Count(item => item.IsParticipating));
        MembershipRecord? joined = null;
        try { joined = await memberships.CreateAsync(groupId, user.UserId, profile.DisplayName, false, cancellationToken); }
        catch (ConditionalCheckFailedException) { }
        if (joined is not null)
        {
            await audit.RecordAsync(AuditAction.ParticipantJoined, groupId, AuditTarget.Member(joined.MemberId), cancellationToken: cancellationToken);
            await analytics.TrackAsync(AnalyticsEventType.ParticipantJoined, group.Plan, groupId,
                $"participant_joined:{joined.MemberId}",
                new Dictionary<string, string>
                {
                    ["member_count"] = (currentMembers.Count() + 1).ToString(System.Globalization.CultureInfo.InvariantCulture)
                }, cancellationToken);
        }
        return await GetAsync(groupId, cancellationToken);
    }

    public async Task<Membership> GetMyMembershipAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var (_, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        return Private(membership);
    }

    public async Task<Membership> UpdateMyMembershipAsync(string groupId, UpdateMembershipRequest request, CancellationToken cancellationToken = default)
    {
        var (group, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        var updated = await memberships.UpdatePrivateAsync(membership.MemberId,
            Validation.Optional(request.Wishlist ?? membership.Wishlist, 2000),
            Validation.Optional(request.Avoidances ?? membership.Avoidances, 2000),
            request.Address is null ? membership.Address : Validation.Address(request.Address), cancellationToken);
        // Readiness milestone: the member has provided a wish list. The content is never recorded —
        // only the fact of readiness, deduped once per member.
        if (!string.IsNullOrWhiteSpace(updated.Wishlist))
            await analytics.TrackAsync(AnalyticsEventType.ParticipantReady, group.Plan, groupId,
                $"participant_ready:{membership.MemberId}", cancellationToken: cancellationToken);
        return Private(updated);
    }

    public async Task<Membership> ClearMyPrivateDataAsync(string groupId, CancellationToken cancellationToken = default)
    {
        // Participant self-service: erase my own wishlist, avoidances, and mailing address for this
        // exchange. Allowed at any time (open or drawn) — it is the participant's own data. Clearing
        // already-empty fields is a harmless no-op, so the action is idempotent.
        var (_, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        // Structured wishes are the same category of data as the free-text list this control was
        // written for, so "erase my wishlist" has to mean both or the button quietly under-delivers.
        await wishes.DeleteByMemberAsync(membership.MemberId, cancellationToken);
        var cleared = await memberships.UpdatePrivateAsync(membership.MemberId, "", "", new Address(), cancellationToken);
        await audit.RecordAsync(AuditAction.ParticipantDataCleared, groupId, AuditTarget.Member(membership.MemberId), cancellationToken: cancellationToken);
        return Private(cleared);
    }

    public async Task LeaveAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var (group, membership) = await RequireMembershipAsync(groupId, cancellationToken); RequireOpen(group);
        if (membership.IsOrganizer) throw ApiException.Conflict("The organizer must delete the group instead of leaving it.");
        // Before the membership row goes: member_id is the only key these rows have, so deleting the
        // membership first would strand them with nothing able to address them again.
        await wishes.DeleteByMemberAsync(membership.MemberId, cancellationToken);
        await memberships.DeleteAsync(membership.MemberId, cancellationToken);
        await audit.RecordAsync(AuditAction.ParticipantLeft, groupId, AuditTarget.Member(membership.MemberId), cancellationToken: cancellationToken);
        var remaining = group.Exclusions.Where(pair => !pair.Contains(membership.MemberId, StringComparer.Ordinal)).ToList();
        if (remaining.Count != group.Exclusions.Count)
            await ConditionalGroupUpdate(() => groups.UpdateAsync(groupId,
                new Dictionary<string, AttributeValue> { ["exclusions"] = DynamoValues.ExclusionsValue(remaining) },
                GroupStatus.Open, cancellationToken));
    }

    public async Task<Membership> UpdateParticipationAsync(string groupId, string memberId, ParticipationRequest request, CancellationToken cancellationToken = default)
    {
        var (group, actor) = await RequireMembershipAsync(groupId, cancellationToken); RequireOrganizer(actor); RequireOpen(group);
        var member = await memberships.GetAsync(memberId, cancellationToken);
        if (member is null || member.GroupId != groupId) throw ApiException.NotFound("Participant not found.");
        if (request.IsParticipating is null) throw ApiException.BadRequest("is_participating must be true or false.");
        if (member.IsOrganizer && !request.IsParticipating.Value) throw ApiException.Conflict("The organizer must participate in the exchange.");
        if (request.IsParticipating.Value && !member.IsParticipating)
        {
            var currentMembers = await memberships.GetByGroupAsync(groupId, cancellationToken);
            plans.EnsureParticipantCapacity(
                group.Plan, group.EntitlementId, currentMembers.Count(item => item.IsParticipating));
        }
        var updated = await memberships.UpdateParticipationAsync(memberId, request.IsParticipating.Value, cancellationToken);
        await audit.RecordAsync(AuditAction.ParticipationChanged, groupId, AuditTarget.Member(memberId),
            new Dictionary<string, string> { ["is_participating"] = request.IsParticipating.Value ? "true" : "false" }, cancellationToken: cancellationToken);
        return Public(updated);
    }

    public async Task<Membership> UpdateOrganizerRoleAsync(
        string groupId,
        string memberId,
        OrganizerRoleRequest request,
        CancellationToken cancellationToken = default)
    {
        var (group, _) = await RequireMembershipAsync(groupId, cancellationToken);
        RequireOwner(group);
        plans.EnsureCapability(group.Plan, group.EntitlementId, PlanCapability.CoOrganizers);
        if (request.IsOrganizer is null)
            throw ApiException.BadRequest("is_organizer must be true or false.");
        var member = await memberships.GetAsync(memberId, cancellationToken);
        if (member is null || member.GroupId != groupId)
            throw ApiException.NotFound("Participant not found.");
        if (member.UserId == group.OwnerUserId && !request.IsOrganizer.Value)
            throw ApiException.Conflict("The exchange owner cannot be removed as an organizer.");
        var updated = await memberships.UpdateOrganizerAsync(memberId, request.IsOrganizer.Value, cancellationToken);
        await audit.RecordAsync(
            AuditAction.RoleChanged,
            groupId,
            AuditTarget.Role(memberId),
            new Dictionary<string, string>
            {
                ["role"] = request.IsOrganizer.Value ? "co_organizer" : "participant"
            },
            cancellationToken: cancellationToken);
        return Public(updated, group);
    }

    public async Task<GroupDetail> SetExclusionsAsync(string groupId, ExclusionsRequest request, CancellationToken cancellationToken = default)
    {
        var (group, actor) = await RequireMembershipAsync(groupId, cancellationToken); RequireOrganizer(actor); RequireOpen(group);
        if (request.Exclusions is null) throw ApiException.BadRequest("exclusions must be a list of participant pairs.");
        var memberIds = (await memberships.GetByGroupAsync(groupId, cancellationToken)).Select(item => item.MemberId).ToHashSet(StringComparer.Ordinal);
        var normalized = new List<string[]>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var pair in request.Exclusions)
        {
            if (pair.Length != 2 || pair[0] == pair[1]) throw ApiException.BadRequest("Each exclusion must contain two different participants.");
            if (!memberIds.Contains(pair[0]) || !memberIds.Contains(pair[1])) throw ApiException.BadRequest("An exclusion references an unknown participant.");
            var ordered = pair.Order(StringComparer.Ordinal).ToArray();
            if (seen.Add($"{ordered[0]}\0{ordered[1]}")) normalized.Add(ordered);
        }
        await ConditionalGroupUpdate(() => groups.UpdateAsync(groupId,
            new Dictionary<string, AttributeValue> { ["exclusions"] = DynamoValues.ExclusionsValue(normalized) }, GroupStatus.Open, cancellationToken));
        await audit.RecordAsync(AuditAction.ExclusionsChanged, groupId, AuditTarget.Group(groupId),
            new Dictionary<string, string> { ["exclusion_count"] = normalized.Count.ToString(System.Globalization.CultureInfo.InvariantCulture) }, cancellationToken: cancellationToken);
        return await GetAsync(groupId, cancellationToken);
    }

    public async Task<RecipientAssignment> DrawAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var (group, actor) = await RequireMembershipAsync(groupId, cancellationToken); RequireOrganizer(actor); RequireOpen(group);
        var assignments = matching.CreateAssignments(
            (await memberships.GetByGroupAsync(groupId, cancellationToken)).Where(item => item.IsParticipating).Select(item => item.MemberId), group.Exclusions);
        try { await groups.CreateDrawAsync(groupId, assignments, user.UserId, cancellationToken); }
        catch (TransactionCanceledException) { throw ApiException.Conflict("This group has already been drawn or changed."); }
        await audit.RecordAsync(AuditAction.DrawCreated, groupId, AuditTarget.Draw(groupId),
            new Dictionary<string, string> { ["participant_count"] = assignments.Count.ToString(System.Globalization.CultureInfo.InvariantCulture) }, cancellationToken: cancellationToken);
        await analytics.TrackAsync(AnalyticsEventType.DrawCompleted, group.Plan, groupId,
            $"draw_completed:{groupId}",
            new Dictionary<string, string>
            {
                ["participant_count"] = assignments.Count.ToString(System.Globalization.CultureInfo.InvariantCulture),
                ["days_to_draw"] = DaysSince(group.CreatedAt).ToString(System.Globalization.CultureInfo.InvariantCulture)
            }, cancellationToken);
        return await GetAssignmentAsync(groupId, cancellationToken: cancellationToken);
    }

    public async Task<GroupDetail> ResetAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var (group, actor) = await RequireMembershipAsync(groupId, cancellationToken); RequireOrganizer(actor);
        if (group.Status != GroupStatus.Drawn) throw ApiException.Conflict("This group has not been drawn.");
        try { await groups.ResetDrawAsync(groupId, cancellationToken); }
        catch (TransactionCanceledException) { throw ApiException.Conflict("The draw was already reset or changed."); }
        await audit.RecordAsync(AuditAction.DrawReset, groupId, AuditTarget.Draw(groupId), cancellationToken: cancellationToken);
        return await GetAsync(groupId, cancellationToken);
    }

    public async Task<RecipientAssignment> GetAssignmentAsync(
        string groupId,
        string? drawVersion = null,
        CancellationToken cancellationToken = default)
    {
        var (group, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        if (group.Status != GroupStatus.Drawn) throw ApiException.Conflict("Assignments have not been created yet.");
        var draw = await groups.GetDrawAsync(groupId, cancellationToken);
        if (!string.IsNullOrWhiteSpace(drawVersion) && draw?.DrawId != drawVersion)
            throw ApiException.Conflict("This assignment link is obsolete. Open the exchange again for fresh assignment access.");
        if (draw is null || !draw.Assignments.TryGetValue(membership.MemberId, out var recipientId))
            throw ApiException.NotFound("You do not have an assignment in this draw.");
        var recipient = await memberships.GetAsync(recipientId, cancellationToken)
            ?? throw ApiException.NotFound("Your assigned participant could not be found.");
        // Assignment view milestone — recorded once per member; the assignment itself is never recorded.
        await analytics.TrackAsync(AnalyticsEventType.AssignmentViewed, group.Plan, groupId,
            $"assignment_viewed:{membership.MemberId}", cancellationToken: cancellationToken);
        // And durably, on the membership row, because the organizer dashboard reads it back (#133).
        // The analytics sink cannot answer this: it is deduplicated, it can be switched off by
        // configuration, and a product surface must not change meaning when telemetry is disabled.
        // Written only on the first view of this draw, so re-reading an assignment is a pure read.
        if (membership.AssignmentViewedDrawId != draw.DrawId)
            await memberships.MarkAssignmentViewedAsync(membership.MemberId, draw.DrawId, cancellationToken);
        return Assignment(recipient, await wishes.GetByMemberAsync(recipient.MemberId, cancellationToken));
    }

    public Task<RecipientAssignment> GetAssignmentAsync(
        string groupId,
        CancellationToken cancellationToken = default) =>
        GetAssignmentAsync(groupId, null, cancellationToken);

    public async Task<RevealResponse> RevealAsync(string groupId, RevealRequest request, CancellationToken cancellationToken = default)
    {
        var (group, _) = await RequireMembershipAsync(groupId, cancellationToken); RequireOwner(group);
        if (group.Status != GroupStatus.Drawn) throw ApiException.Conflict("Assignments have not been created yet.");
        var reason = Validation.Required(request.Reason, "reason", 500);
        var draw = await groups.GetDrawAsync(groupId, cancellationToken) ?? throw ApiException.NotFound("Draw record not found.");
        await audit.RecordAsync(AuditAction.AssignmentRevealed, groupId, AuditTarget.Group(groupId),
            new Dictionary<string, string> { ["reason"] = reason }, cancellationToken: cancellationToken);
        var members = (await memberships.GetByGroupAsync(groupId, cancellationToken)).ToDictionary(item => item.MemberId, StringComparer.Ordinal);
        var pairs = draw.Assignments.Where(pair => members.ContainsKey(pair.Key) && members.ContainsKey(pair.Value))
            .ToList();
        var revealed = new List<RevealAssignment>(pairs.Count);
        foreach (var pair in pairs)
        {
            var recipient = members[pair.Value];
            revealed.Add(new RevealAssignment(
                Public(members[pair.Key]),
                Assignment(recipient, await wishes.GetByMemberAsync(recipient.MemberId, cancellationToken))));
        }
        return new RevealResponse(revealed);
    }

    private async Task<GroupRecord> RequireGroupAsync(string groupId, CancellationToken cancellationToken) =>
        await groups.GetAsync(groupId, cancellationToken) ?? throw ApiException.NotFound("Group not found.");
    private async Task<(GroupRecord Group, MembershipRecord Membership)> RequireMembershipAsync(string groupId, CancellationToken cancellationToken)
    {
        var group = await RequireGroupAsync(groupId, cancellationToken);
        var membership = await memberships.GetByUserAndGroupAsync(user.UserId, groupId, cancellationToken)
            ?? throw ApiException.Forbidden("You are not a member of this group.");
        return (group, membership);
    }
    private static void RequireOrganizer(MembershipRecord member) { if (!member.IsOrganizer) throw ApiException.Forbidden("Only the organizer can perform this action."); }
    private void RequireOwner(GroupRecord group) { if (group.OwnerUserId != user.UserId) throw ApiException.Forbidden("Only the exchange owner can perform this action."); }
    private static void RequireOpen(GroupRecord group) { if (group.Status != GroupStatus.Open) throw ApiException.Conflict("Reset the draw before changing the roster or matching rules."); }
    private static async Task ConditionalGroupUpdate(Func<Task<GroupRecord>> operation)
    {
        try { await operation(); } catch (ConditionalCheckFailedException) { throw ApiException.Conflict("This group has already been drawn or changed."); }
    }

    private GroupDetail Detail(GroupRecord group, MembershipRecord member, IReadOnlyList<MembershipRecord> all) => new(
        group.GroupId, group.Name, group.Status, group.EventDate, Amount(group.SpendingLimitCents), group.Currency,
        group.Plan, plans.Get(group.Plan).ParticipantLimit, member.IsOrganizer, member.UserId == group.OwnerUserId, group.CreatedAt, group.UpdatedAt, group.Description, group.SignupDeadline,
        member.IsOrganizer ? group.Exclusions : [], all.Select(item => Public(item, group)).ToList(),
        Customization: group.Customization, RequiresAddress: group.RequiresAddress);
    private GroupSummary Summary(GroupRecord group, MembershipRecord member) => new(
        group.GroupId, group.Name, group.Status, group.EventDate, Amount(group.SpendingLimitCents), group.Currency,
        group.Plan, plans.Get(group.Plan).ParticipantLimit, member.IsOrganizer, member.UserId == group.OwnerUserId,
        group.CreatedAt, group.UpdatedAt, group.RequiresAddress);
    private static Membership Public(MembershipRecord member, GroupRecord? group = null) => new(
        member.MemberId,
        member.DisplayName,
        member.IsOrganizer,
        member.IsParticipating,
        IsOwner: group is not null && member.UserId == group.OwnerUserId,
        IsReady: !string.IsNullOrWhiteSpace(member.Wishlist));
    private static Membership Private(MembershipRecord member) => new(
        member.MemberId,
        member.DisplayName,
        member.IsOrganizer,
        member.IsParticipating,
        member.Wishlist,
        member.Avoidances,
        member.Address,
        IsReady: !string.IsNullOrWhiteSpace(member.Wishlist));
    // The giver's view of their recipient. Projected through RecipientWish rather than Wish so that
    // owner-only state added later (purchase claims, #130) cannot reach this path by default.
    private static RecipientAssignment Assignment(MembershipRecord member, IReadOnlyList<WishRecord> wishes) => new(
        member.MemberId, member.DisplayName, member.Wishlist, member.Avoidances, member.Address,
        wishes.Select(RecipientWishOf).ToList());
    private static RecipientWish RecipientWishOf(WishRecord record) => new(
        record.WishId, record.Kind, record.Title,
        Empty(record.Url), Empty(record.ImageUrl), record.PriceCents,
        record.PriceCents is null ? null : Empty(record.Currency),
        record.Quantity, record.Priority, Empty(record.Details), record.Position);
    private static string? Empty(string value) => string.IsNullOrWhiteSpace(value) ? null : value;
    private static decimal? Amount(long? cents) => cents is null ? null : cents.Value / 100m;
    private static long DaysSince(string isoTimestamp) =>
        DateTimeOffset.TryParse(isoTimestamp, System.Globalization.CultureInfo.InvariantCulture,
            System.Globalization.DateTimeStyles.RoundtripKind, out var created)
            ? Math.Max(0, (long)(DateTimeOffset.UtcNow - created).TotalDays)
            : 0;
    private static string NewSecret() => WebEncoders.Base64UrlEncode(RandomNumberGenerator.GetBytes(32));
    private static string Hash(string secret) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(secret))).ToLowerInvariant();
    private string InviteUrl(string groupId, string secret) => $"{settings.AppBaseUrl}/join/{groupId}#invite={secret}";
}
