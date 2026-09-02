using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services.Email.Core;
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
    Task<RepeatedExchange> RepeatAsync(string groupId, RepeatExchangeRequest request, CancellationToken cancellationToken = default);
    Task<GroupDetail> UpdateCustomizationAsync(string groupId, UpdateCustomizationRequest request, CancellationToken cancellationToken = default);
    Task<InvitationPreview> GetInvitationAsync(string groupId, string? inviteToken, CancellationToken cancellationToken = default);
    Task DeleteAsync(string groupId, CancellationToken cancellationToken = default);
    Task<InviteResponse> RotateInviteAsync(string groupId, CancellationToken cancellationToken = default);
    Task<GroupDetail> JoinAsync(string groupId, JoinGroupRequest request, CancellationToken cancellationToken = default);
    Task<Membership> GetMyMembershipAsync(string groupId, CancellationToken cancellationToken = default);
    Task<Membership> UpdateMyMembershipAsync(string groupId, UpdateMembershipRequest request, CancellationToken cancellationToken = default);
    Task<Membership> ClearMyPrivateDataAsync(string groupId, CancellationToken cancellationToken = default);
    Task LeaveAsync(string groupId, CancellationToken cancellationToken = default);
    Task RemoveMemberAsync(string groupId, string memberId, CancellationToken cancellationToken = default);
    Task<Membership> UpdateParticipationAsync(string groupId, string memberId, ParticipationRequest request, CancellationToken cancellationToken = default);
    Task<Membership> UpdateOrganizerRoleAsync(string groupId, string memberId, OrganizerRoleRequest request, CancellationToken cancellationToken = default);
    Task<GroupDetail> SetExclusionsAsync(string groupId, ExclusionsRequest request, CancellationToken cancellationToken = default);
    Task<RecipientAssignment> DrawAsync(string groupId, CancellationToken cancellationToken = default);
    Task<GroupDetail> ResetAsync(string groupId, CancellationToken cancellationToken = default);
    Task<RecipientAssignment> GetAssignmentAsync(string groupId, CancellationToken cancellationToken = default);
    Task<RecipientAssignment> GetAssignmentAsync(string groupId, string? drawVersion, CancellationToken cancellationToken = default);
    Task<RevealResponse> RevealAsync(string groupId, RevealRequest request, CancellationToken cancellationToken = default);
    Task<RecipientAssignment> SetWishClaimAsync(string groupId, string wishId, SetWishClaimRequest request, CancellationToken cancellationToken = default);
    Task<RecipientAssignment> ReleaseWishClaimAsync(string groupId, string wishId, CancellationToken cancellationToken = default);
    Task<RecipientAssignment> SetGiftStageAsync(string groupId, SetGiftStageRequest request, CancellationToken cancellationToken = default);
    Task<GiftReceipt> GetGiftReceiptAsync(string groupId, CancellationToken cancellationToken = default);
    Task<GiftReceipt> SetGiftReceivedAsync(string groupId, SetGiftReceivedRequest request, CancellationToken cancellationToken = default);
}

internal sealed class GroupService(
    ICurrentUser user,
    IProfileRepository profiles,
    IGroupRepository groups,
    IMembershipRepository memberships,
    IWishRepository wishes,
    IQuestionRepository questions,
    IInvitationRepository invitations,
    IMatchingService matching,
    IPlanCatalog plans,
    IAuditTrail audit,
    IProductAnalytics analytics,
    IAccountDirectory directory,
    ITransactionalEmailService email,
    ITransactionalEmailTemplates emailTemplates,
    ILogger<GroupService> logger,
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

    /// <summary>
    /// Starts a new exchange from a previous one (#136).
    /// </summary>
    /// <remarks>
    /// <para>
    /// Free, and available to any owner. It creates a NEW exchange rather than reopening the old one,
    /// so last year stays exactly as it was — the source is only ever read.
    /// </para>
    /// <para>
    /// **Nothing private travels.** Not assignments, addresses, wishlists, purchase claims,
    /// conversations or gift progress — and not because each is filtered out, but because the new
    /// exchange has no memberships except the organizer's. There is nowhere for any of it to land.
    /// What carries over is what the organizer typed: the name, the description, the instructions,
    /// the spending limit, and optionally the pairs who should not draw each other.
    /// </para>
    /// <para>
    /// **Nobody is enrolled.** The prior participants come back as a list of names so the organizer
    /// knows who to send the link to; joining is the same act it always was. Silently enrolling last
    /// year's roster would put people in an exchange they never agreed to and hand them a place in a
    /// draw they might not want.
    /// </para>
    /// </remarks>
    public async Task<RepeatedExchange> RepeatAsync(
        string groupId,
        RepeatExchangeRequest request,
        CancellationToken cancellationToken = default)
    {
        var source = await RequireGroupAsync(groupId, cancellationToken);
        if (source.OwnerUserId != user.UserId)
            throw ApiException.Forbidden("Only the owner of an exchange can repeat it.");
        var profile = await profiles.GetAsync(user.UserId, cancellationToken)
            ?? throw ApiException.Conflict("Complete your profile before creating a group.");

        var roster = await memberships.GetByGroupAsync(groupId, cancellationToken);
        var dates = Validation.GroupDates(request.EventDate, request.SignupDeadline);
        var secret = NewSecret();
        var now = DateTimeOffset.UtcNow.ToString("O");
        var newGroupId = Guid.NewGuid().ToString();

        var group = new GroupRecord(
            newGroupId,
            user.UserId,
            Validation.Required(request.Name ?? source.Name, "name", 120),
            request.CopyDetails ? source.Description : "",
            dates.EventDate,
            dates.SignupDeadline,
            request.CopyDetails ? source.SpendingLimitCents : null,
            "USD",
            // Always Free. Plus is bought per exchange and does not travel — repeating one would
            // otherwise be a way to get it for nothing.
            PlanCode.Free,
            null,
            GroupStatus.Open,
            Hash(secret),
            request.CopyExclusions ? TranslateExclusions(source, roster, newGroupId) : [],
            now,
            now,
            // Customization is Plus branding and the new exchange is Free; carrying it over would
            // hand out a paid capability. RequiresAddress is a fact about how THIS exchange hands
            // gifts over, which the organizer decides again.
            Customization: null,
            RequiresAddress: false,
            Instructions: request.CopyDetails ? source.Instructions : "");

        await groups.CreateAsync(group, cancellationToken);
        await memberships.CreateAsync(group.GroupId, user.UserId, profile.DisplayName, true, cancellationToken);
        await audit.RecordAsync(AuditAction.GroupCreated, group.GroupId, AuditTarget.Group(group.GroupId),
            new Dictionary<string, string> { ["repeated_from"] = groupId }, cancellationToken: cancellationToken);
        await analytics.TrackAsync(AnalyticsEventType.RepeatExchangeCreated, group.Plan, group.GroupId,
            $"repeat_exchange:{group.GroupId}", cancellationToken: cancellationToken);

        return new RepeatedExchange(
            await GetAsync(group.GroupId, cancellationToken),
            InviteUrl(group.GroupId, secret),
            roster
                .Where(member => member.UserId != user.UserId)
                .Select(member => member.DisplayName)
                .OrderBy(name => name, StringComparer.CurrentCultureIgnoreCase)
                .ToList());
    }

    /// <summary>
    /// Rewrites the source's exclusions into the new exchange's member ids.
    /// </summary>
    /// <remarks>
    /// A member id is <c>sha256(groupId:userId)</c>, so what somebody's id WILL be in the new
    /// exchange is known before they join — which is what makes carrying the pairs over possible at
    /// all, given that a literal copy would name ids belonging to last year's group.
    ///
    /// A pair is kept only when both sides still resolve to an account: somebody whose membership is
    /// gone, or was anonymized by an account deletion, takes their pairs with them rather than
    /// leaving a constraint nobody can explain. Until both people join, the pair simply names
    /// non-members, and the matcher ignores it.
    /// </remarks>
    private static IReadOnlyList<string[]> TranslateExclusions(
        GroupRecord source,
        IReadOnlyList<MembershipRecord> roster,
        string newGroupId)
    {
        var users = roster.ToDictionary(member => member.MemberId, member => member.UserId, StringComparer.Ordinal);
        return source.Exclusions
            .Where(pair => pair.Length == 2 && pair.All(users.ContainsKey))
            .Select(pair => pair
                .Select(memberId => Data.MembershipRepository.MemberId(newGroupId, users[memberId]))
                .ToArray())
            .ToList();
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
            // Counts only, and only after a draw. Before one there is nothing to aggregate and null
            // says exactly that — see GiftProgress on why this is not three zeroes.
            draw is null ? null : Progress(members, draw.DrawId));
    }

    /// <summary>
    /// The organizer's gift roll-up (#132): three cumulative counts over the participating roster.
    /// </summary>
    /// <remarks>
    /// Cumulative, because the stages are a journey rather than buckets: a gift already sent still
    /// counts as purchased, and one confirmed received counts as both — an organizer reading
    /// "4 purchased, 1 sent" would otherwise conclude four gifts are sitting in hallways when three
    /// are in the post.
    ///
    /// Counts only. Not a name, not a pairing, not a wish — this is the same response that refuses
    /// to say what is on anybody's list.
    /// </remarks>
    private static GiftProgress Progress(IReadOnlyList<MembershipRecord> members, string drawId)
    {
        var participating = members.Where(member => member.IsParticipating).ToList();
        var current = participating.Where(member => member.GiftProgressDrawId == drawId).ToList();
        var received = current.Count(member => member.GiftReceivedAt is not null);
        var sent = current.Count(member =>
            member.GiftStage == GiftStage.Sent || member.GiftReceivedAt is not null);
        var purchased = current.Count(member =>
            member.GiftStage is GiftStage.Purchased or GiftStage.Sent || member.GiftReceivedAt is not null);
        return new GiftProgress(purchased, sent, received, participating.Count);
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
        // How the exchange works, for people who have already joined (#135). Free and ungated — an
        // exchange that cannot tell its participants where to bring the gift does not work at any
        // price. NOT the customization's instructions, which are invitation copy; see GroupRecord.
        if (request.Instructions is not null)
            fields["instructions"] = DynamoValues.S(Validation.Optional(request.Instructions, 2000));
        if (fields.Count > 0)
        {
            try
            {
                await groups.UpdateAsync(
                    groupId, fields, expectedUpdatedAt: request.ExpectedUpdatedAt, cancellationToken: cancellationToken);
            }
            catch (ConditionalCheckFailedException)
            {
                // Two organizers editing at once. Refusing is the only honest answer: a last-write
                // wins would silently discard whatever the other one just saved, and neither of them
                // would ever know it happened.
                throw ApiException.Conflict(
                    "Somebody else changed this exchange while you were editing. Reload and try again.");
            }
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
        // Conversations first: they are keyed by group and draw, so once the group row is gone
        // nothing can enumerate them again. Two people's words, and neither is the organizer's.
        await questions.DeleteByGroupAsync(groupId, cancellationToken);
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
            new Dictionary<string, AttributeValue> { ["invite_hash"] = DynamoValues.S(Hash(secret)) }, GroupStatus.Open, cancellationToken: cancellationToken));
        await audit.RecordAsync(AuditAction.InviteRotated, groupId, AuditTarget.Invite(groupId), cancellationToken: cancellationToken);
        // Deduped per group: a group has "an invite" whether it was rotated once or many times.
        await analytics.TrackAsync(AnalyticsEventType.InviteSent, group.Plan, groupId,
            $"invite_sent:{groupId}", cancellationToken: cancellationToken);
        return new InviteResponse(InviteUrl(groupId, secret));
    }

    public async Task<GroupDetail> JoinAsync(string groupId, JoinGroupRequest request, CancellationToken cancellationToken = default)
    {
        var group = await RequireGroupAsync(groupId, cancellationToken);
        // Somebody already in the exchange following their link again is not an error — they land
        // back on the exchange. Checked BEFORE the draw check, so a member returning to an invite
        // after the draw is let through to the exchange they are already part of.
        if (await memberships.GetByUserAndGroupAsync(user.UserId, groupId, cancellationToken) is not null)
            return await GetAsync(groupId, cancellationToken);
        // `RequireOpen`'s message is written for an organizer changing the roster and tells a
        // would-be joiner to reset a draw they have no power over. The refusal is the same; what
        // they are told about it is not.
        if (group.Status != GroupStatus.Open)
            throw ApiException.Conflict("This exchange has already been drawn, so it is closed to new members.");
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
        // The claims are the caller's own data too — notes they authored about their own shopping —
        // and the control says "clear everything I saved". Leaving them would make it a lie.
        await memberships.ClearWishClaimsAsync(membership.MemberId, cancellationToken);
        // Both halves of their gift progress: the stage they set on their own gift, and the "it
        // arrived" they put on their giver's row. The second lives somewhere else by design, so
        // "clear everything I saved" has to go and find it.
        await ClearGiftProgressBothWaysAsync(groupId, membership.MemberId, cancellationToken);
        // And the conversations they are party to, on both sides: the thread about their own list,
        // and the one they opened with the person they were assigned.
        await questions.DeleteForMemberAsync(
            groupId, membership.MemberId, await ThreadsGivenByAsync(groupId, membership.MemberId, cancellationToken),
            cancellationToken);
        var cleared = await memberships.UpdatePrivateAsync(membership.MemberId, "", "", new Address(), cancellationToken);
        await audit.RecordAsync(AuditAction.ParticipantDataCleared, groupId, AuditTarget.Member(membership.MemberId), cancellationToken: cancellationToken);
        return Private(cleared);
    }

    public async Task LeaveAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var (group, membership) = await RequireMembershipAsync(groupId, cancellationToken); RequireOpen(group);
        if (membership.IsOrganizer) throw ApiException.Conflict("The organizer must delete the group instead of leaving it.");
        await RemoveMembershipAsync(group, membership, AuditAction.ParticipantLeft, cancellationToken);
    }

    /// <summary>
    /// An organizer removes somebody else, before the draw (#135).
    /// </summary>
    /// <remarks>
    /// Only the owner. A co-organizer helps run the exchange; deciding who is in it is the sort of
    /// thing #205 kept for the owner, and this follows that precedent rather than inventing another.
    ///
    /// The organizer cannot remove themselves through this route — they would be deleting the
    /// exchange out from under everybody, and there is a control for that which says so.
    /// </remarks>
    public async Task RemoveMemberAsync(string groupId, string memberId, CancellationToken cancellationToken = default)
    {
        var (group, actor) = await RequireMembershipAsync(groupId, cancellationToken);
        RequireOrganizer(actor);
        RequireOwner(group);
        // Before the draw only. Afterwards a completed draw references the member row, and removing
        // it would leave somebody buying for a person who is no longer there — reset first.
        RequireOpen(group);
        if (memberId == actor.MemberId)
            throw ApiException.Conflict("Delete the exchange instead of removing yourself from it.");
        var member = await memberships.GetAsync(memberId, cancellationToken);
        if (member is null || member.GroupId != groupId)
            throw ApiException.NotFound("That participant is not in this exchange.");

        await RemoveMembershipAsync(group, member, AuditAction.ParticipantRemoved, cancellationToken);
    }

    /// <summary>
    /// Everything that has to go when somebody stops being a member, in one place.
    /// </summary>
    /// <remarks>
    /// There are three ways out of an exchange — leaving, being removed, and deleting your account —
    /// and what they have to sweep has grown every release: wishes (#127), purchase claims (#130),
    /// question threads at both ends (#131), gift progress on two rows (#132). Three copies of that
    /// list would drift, and the one that drifted would leave somebody's words behind.
    /// <see cref="AccountDeletionService"/> keeps its own because it also anonymizes rather than
    /// deletes; the two are checked against each other by test rather than shared, because their
    /// endings genuinely differ.
    /// </remarks>
    private async Task RemoveMembershipAsync(
        GroupRecord group,
        MembershipRecord member,
        AuditAction action,
        CancellationToken cancellationToken)
    {
        // Before the membership row goes: member_id is the only key these rows have, so deleting the
        // membership first would strand them with nothing able to address them again.
        await wishes.DeleteByMemberAsync(member.MemberId, cancellationToken);
        await questions.DeleteForMemberAsync(
            group.GroupId, member.MemberId,
            await ThreadsGivenByAsync(group.GroupId, member.MemberId, cancellationToken),
            cancellationToken);
        await ClearGiftProgressBothWaysAsync(group.GroupId, member.MemberId, cancellationToken);
        await memberships.DeleteAsync(member.MemberId, cancellationToken);
        await audit.RecordAsync(action, group.GroupId, AuditTarget.Member(member.MemberId), cancellationToken: cancellationToken);
        await PruneExclusionsAsync(group, member.MemberId, cancellationToken);
    }

    /// <summary>
    /// Drops every pair naming a member who is no longer here.
    /// </summary>
    /// <remarks>
    /// A stale pair is not inert. The matcher reads exclusions as constraints, so one naming a member
    /// id that no longer exists narrows the search for no reason and, on a small roster, can make an
    /// otherwise solvable draw impossible — with an error message about the draw rather than about
    /// the person who left three weeks earlier.
    /// </remarks>
    private async Task PruneExclusionsAsync(GroupRecord group, string memberId, CancellationToken cancellationToken)
    {
        var remaining = group.Exclusions
            .Where(pair => !pair.Contains(memberId, StringComparer.Ordinal))
            .ToList();
        if (remaining.Count == group.Exclusions.Count) return;
        await ConditionalGroupUpdate(() => groups.UpdateAsync(group.GroupId,
            new Dictionary<string, AttributeValue> { ["exclusions"] = DynamoValues.ExclusionsValue(remaining) },
            GroupStatus.Open, cancellationToken: cancellationToken));
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
            new Dictionary<string, AttributeValue> { ["exclusions"] = DynamoValues.ExclusionsValue(normalized) }, GroupStatus.Open, cancellationToken: cancellationToken));
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
        await NotifyDrawCompletedAsync(group, assignments.Keys, cancellationToken);
        return await GetAssignmentAsync(groupId, cancellationToken: cancellationToken);
    }

    /// <summary>
    /// Tells everyone in the draw that their assignment is ready (#137).
    /// </summary>
    /// <remarks>
    /// Essential mail, so it is not suppressed by the non-essential opt-out — this is the one message
    /// without which the exchange does not work. It carries no recipient name: the whole point of the
    /// link is that the name is behind a sign-in, and putting it in an inbox would undo that.
    ///
    /// Best-effort in every direction. The draw has already been written and audited by the time this
    /// runs, so a mail failure must not fail it, and one address that cannot be resolved must not
    /// stop the other forty-nine.
    /// </remarks>
    private async Task NotifyDrawCompletedAsync(
        GroupRecord group,
        IEnumerable<string> memberIds,
        CancellationToken cancellationToken)
    {
        var roster = (await memberships.GetByGroupAsync(group.GroupId, cancellationToken))
            .ToDictionary(member => member.MemberId, StringComparer.Ordinal);
        foreach (var memberId in memberIds)
        {
            if (!roster.TryGetValue(memberId, out var member)) continue;
            try
            {
                var address = await directory.VerifiedEmailAsync(member.UserId, cancellationToken);
                if (string.IsNullOrWhiteSpace(address)) continue;
                await email.SendAsync(
                    emailTemplates.DrawCompleted(new DrawCompletedEmail(
                        // One id per member per draw, so a retried draw notification is de-duplicated
                        // by the message ledger rather than sent twice.
                        $"draw:{group.GroupId}:{memberId}",
                        address,
                        member.DisplayName,
                        group.Name,
                        new Uri($"{settings.AppBaseUrl}/groups/{group.GroupId}"),
                        group.Customization)),
                    cancellationToken);
            }
            catch (Exception exception)
            {
                logger.LogWarning(exception, "Could not send a draw notification to a participant.");
            }
        }
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
        return Assignment(
            recipient,
            await wishes.GetByMemberAsync(recipient.MemberId, cancellationToken),
            ClaimsFor(membership, draw.DrawId),
            StatusFor(membership, draw.DrawId));
    }

    /// <summary>
    /// Marks a wish on the caller's assigned list as planned or purchased (#130).
    /// </summary>
    /// <remarks>
    /// The route hangs off <c>assignment</c> because the assignment IS the authorization: the only
    /// list you may claim on is the one your draw entitles you to read, and every check below is
    /// resolved from the caller's own membership rather than from anything the request names.
    /// </remarks>
    public async Task<RecipientAssignment> SetWishClaimAsync(
        string groupId,
        string wishId,
        SetWishClaimRequest request,
        CancellationToken cancellationToken = default)
    {
        var (membership, draw, recipient) = await RequireAssignmentAsync(groupId, cancellationToken);
        var wish = await wishes.GetAsync(recipient.MemberId, wishId, cancellationToken)
            ?? throw ApiException.NotFound("That wish is not on your recipient's list.");

        var state = request.State?.Trim().ToLowerInvariant() switch
        {
            null or "" or "planned" => WishClaimState.Planned,
            "purchased" => WishClaimState.Purchased,
            _ => throw ApiException.BadRequest("state must be 'planned' or 'purchased'.")
        };
        // Defaults to the whole wish. Claiming more than was asked for is refused rather than
        // clamped: a giver who typed 5 against a quantity of 2 has misread the list, and silently
        // recording 2 would tell them they had done what they meant to.
        var quantity = request.Quantity ?? wish.Quantity;
        if (quantity < 1 || quantity > wish.Quantity)
            throw ApiException.BadRequest(
                $"quantity must be between 1 and {wish.Quantity}, the number asked for.");

        await memberships.SetWishClaimAsync(
            membership.MemberId,
            draw.DrawId,
            wishId,
            new WishClaimRecord(state, quantity, DateTimeOffset.UtcNow.ToString("O")),
            cancellationToken);
        // Deliberately NOT audited. An audit row carries the actor and the target, so recording
        // "this member claimed a wish belonging to that member" would write the draw assignment into
        // the one table an organizer can read. Auditing is never gated on a plan, but it is also
        // never allowed to be the thing that spoils the exchange.
        return await GetAssignmentAsync(groupId, cancellationToken: cancellationToken);
    }

    public async Task<RecipientAssignment> ReleaseWishClaimAsync(
        string groupId,
        string wishId,
        CancellationToken cancellationToken = default)
    {
        var (membership, draw, _) = await RequireAssignmentAsync(groupId, cancellationToken);
        await memberships.RemoveWishClaimAsync(membership.MemberId, draw.DrawId, wishId, cancellationToken);
        return await GetAssignmentAsync(groupId, cancellationToken: cancellationToken);
    }

    /// <summary>
    /// The giver moves their own gift along: choosing, purchased, sent (#132).
    /// </summary>
    /// <remarks>
    /// Three stages, not four. "Received" is the recipient's, and lives in its own field — a single
    /// ordered enum would either refuse the gift handed over at a party (never marked sent) or let
    /// the recipient overwrite the giver's record of what they actually did.
    /// </remarks>
    public async Task<RecipientAssignment> SetGiftStageAsync(
        string groupId,
        SetGiftStageRequest request,
        CancellationToken cancellationToken = default)
    {
        var (membership, draw, _) = await RequireAssignmentAsync(groupId, cancellationToken);
        var stage = request.Stage?.Trim().ToLowerInvariant() switch
        {
            "choosing" => GiftStage.Choosing,
            "purchased" => GiftStage.Purchased,
            "sent" => GiftStage.Sent,
            _ => throw ApiException.BadRequest("stage must be 'choosing', 'purchased' or 'sent'."),
        };

        // The one ordering rule that is actually true: a gift somebody has confirmed receiving was
        // obviously bought, so the giver cannot walk it back to "still choosing". Everything else is
        // a legitimate correction — a returned item really does go back to choosing.
        if (Received(membership, draw.DrawId))
            throw ApiException.Conflict("They have already said this arrived, so it cannot move back.");

        await memberships.SetGiftStageAsync(membership.MemberId, draw.DrawId, stage, cancellationToken);
        // Audited, unlike a purchase claim — and safely, because the target is the ACTOR's own member
        // id and the metadata is a stage. Nothing here names the other party, so the trail an
        // organizer may read still cannot be turned into the draw.
        await audit.RecordAsync(
            AuditAction.GiftProgressChanged,
            groupId,
            AuditTarget.Member(membership.MemberId),
            new Dictionary<string, string> { ["stage"] = stage.ToString().ToLowerInvariant() },
            cancellationToken: cancellationToken);
        return await GetAssignmentAsync(groupId, cancellationToken: cancellationToken);
    }

    public async Task<GiftReceipt> GetGiftReceiptAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var (giver, draw) = await RequireGiverOfCallerAsync(groupId, cancellationToken);
        return Receipt(giver, draw.DrawId);
    }

    /// <summary>
    /// The recipient says the gift arrived — or takes it back.
    /// </summary>
    /// <remarks>
    /// Written onto the GIVER's row, whose id is resolved by inverting the draw. The recipient never
    /// learns whose row that was: they send a boolean to <c>members/me</c> and the server does the
    /// rest. Deliberately not ordered after "sent": a gift handed over in person may never have been
    /// marked sent, and refusing the confirmation would make the roll-up wrong to protect a sequence
    /// nobody promised.
    /// </remarks>
    public async Task<GiftReceipt> SetGiftReceivedAsync(
        string groupId,
        SetGiftReceivedRequest request,
        CancellationToken cancellationToken = default)
    {
        var (giver, draw) = await RequireGiverOfCallerAsync(groupId, cancellationToken);
        await memberships.SetGiftReceivedAsync(giver.MemberId, draw.DrawId, request.Received, cancellationToken);
        // The actor is the recipient and the target is the recipient. The giver is not named, which
        // is what keeps this row from being the assignment.
        var (_, actor) = await RequireMembershipAsync(groupId, cancellationToken);
        await audit.RecordAsync(
            AuditAction.GiftProgressChanged,
            groupId,
            AuditTarget.Member(actor.MemberId),
            new Dictionary<string, string> { ["received"] = request.Received ? "true" : "false" },
            cancellationToken: cancellationToken);
        var updated = await memberships.GetAsync(giver.MemberId, cancellationToken);
        return updated is null ? new GiftReceipt(false, null) : Receipt(updated, draw.DrawId);
    }

    /// <summary>The membership row of whoever is giving TO the caller, plus the current draw.</summary>
    /// <remarks>Inverting the draw is the only way to reach it, and the id never leaves this method.</remarks>
    private async Task<(MembershipRecord Giver, DrawRecord Draw)> RequireGiverOfCallerAsync(
        string groupId,
        CancellationToken cancellationToken)
    {
        var (group, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        if (group.Status != GroupStatus.Drawn)
            throw ApiException.Conflict("Assignments have not been created yet.");
        var draw = await groups.GetDrawAsync(groupId, cancellationToken)
            ?? throw ApiException.NotFound("This exchange has no draw.");
        var giverId = draw.Assignments.FirstOrDefault(pair => pair.Value == membership.MemberId).Key;
        if (string.IsNullOrEmpty(giverId))
            throw ApiException.NotFound("Nobody is assigned to you in this draw.");
        return (await memberships.GetAsync(giverId, cancellationToken)
            ?? throw ApiException.NotFound("Your giver could not be found."), draw);
    }

    private static bool Received(MembershipRecord member, string drawId) =>
        member.GiftProgressDrawId == drawId && member.GiftReceivedAt is not null;

    private static GiftReceipt Receipt(MembershipRecord giver, string drawId) =>
        new(Received(giver, drawId), Received(giver, drawId) ? giver.GiftReceivedAt : null);

    /// <summary>
    /// The caller's own gift status, but only for the draw now in force.
    /// </summary>
    /// <remarks>
    /// Same self-invalidation as the claims and the question threads: after a reset the gift you were
    /// preparing may be for somebody else, so the stage starts again at "choosing".
    /// </remarks>
    private static GiftStatus StatusFor(MembershipRecord member, string drawId)
    {
        var current = member.GiftProgressDrawId == drawId;
        var received = Received(member, drawId);
        return new GiftStatus(
            current ? member.GiftStage ?? GiftStage.Choosing : GiftStage.Choosing,
            current ? member.GiftStageAt : null,
            received,
            received ? member.GiftReceivedAt : null,
            !received);
    }

    /// <summary>The caller's membership, the current draw, and the recipient that draw gives them.</summary>
    private async Task<(MembershipRecord Membership, DrawRecord Draw, MembershipRecord Recipient)>
        RequireAssignmentAsync(string groupId, CancellationToken cancellationToken)
    {
        var (group, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        if (group.Status != GroupStatus.Drawn)
            throw ApiException.Conflict("Assignments have not been created yet.");
        var draw = await groups.GetDrawAsync(groupId, cancellationToken);
        if (draw is null || !draw.Assignments.TryGetValue(membership.MemberId, out var recipientId))
            throw ApiException.NotFound("You do not have an assignment in this draw.");
        var recipient = await memberships.GetAsync(recipientId, cancellationToken)
            ?? throw ApiException.NotFound("Your assigned participant could not be found.");
        return (membership, draw, recipient);
    }

    /// <summary>
    /// The caller's claims, but only if they were made under the draw now in force.
    /// </summary>
    /// <remarks>
    /// A reset or a late-participant reassignment mints a new draw id, and the person you are buying
    /// for may have changed. Showing last draw's claims against this draw's list would mark items on
    /// a stranger's wishlist as already bought.
    /// </remarks>
    private static IReadOnlyDictionary<string, WishClaimRecord> ClaimsFor(MembershipRecord member, string drawId) =>
        member.WishClaimsDrawId == drawId && member.WishClaims is { } claims
            ? claims
            : new Dictionary<string, WishClaimRecord>(StringComparer.Ordinal);

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
                // No claims. The organizer is not the giver, and a claim is the giver's private note
                // about their own shopping — an emergency reveal exists to unstick a draw, not to
                // report what everyone has bought.
                Assignment(recipient, await wishes.GetByMemberAsync(recipient.MemberId, cancellationToken))));
        }
        return new RevealResponse(revealed);
    }

    /// <summary>
    /// Clears this member's own gift stage AND the receipt they left on their giver's row.
    /// </summary>
    /// <remarks>
    /// Gift progress is two facts owned by two people about one gift, so removing a member's own
    /// contribution means touching two rows. Their giver's row is reached by inverting the draw —
    /// the same inversion the confirmation itself used, and the only way to find it.
    /// </remarks>
    private async Task ClearGiftProgressBothWaysAsync(
        string groupId,
        string memberId,
        CancellationToken cancellationToken)
    {
        await memberships.ClearGiftProgressAsync(memberId, cancellationToken);
        var draw = await groups.GetDrawAsync(groupId, cancellationToken);
        var giverId = draw?.Assignments.FirstOrDefault(pair => pair.Value == memberId).Key;
        if (!string.IsNullOrEmpty(giverId) && draw is not null)
            await memberships.SetGiftReceivedAsync(giverId, draw.DrawId, false, cancellationToken);
    }

    /// <summary>
    /// The thread ids this member is the GIVER on, in the draw currently in force.
    /// </summary>
    /// <remarks>
    /// A thread is keyed by its recipient, so the recipient's side is found by the member id alone.
    /// The giver's side is not on any row — that is the feature — so the only way to find the
    /// conversation somebody opened is to invert the draw, which is what this does. Both halves are
    /// needed on every removal path: a departing participant's own words are theirs whichever end of
    /// the conversation they wrote from.
    /// </remarks>
    private async Task<IReadOnlyCollection<string>> ThreadsGivenByAsync(
        string groupId,
        string memberId,
        CancellationToken cancellationToken)
    {
        var draw = await groups.GetDrawAsync(groupId, cancellationToken);
        return draw is not null && draw.Assignments.TryGetValue(memberId, out var recipientId)
            ? [QuestionRepository.ThreadId(groupId, draw.DrawId, recipientId)]
            : [];
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
        Customization: group.Customization, RequiresAddress: group.RequiresAddress,
        Instructions: group.Instructions);
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
    private static RecipientAssignment Assignment(
        MembershipRecord member,
        IReadOnlyList<WishRecord> wishes,
        // The CALLER's claims, keyed by wish id. Defaulted to none so every caller that has no
        // business showing claims — the emergency reveal — gets none by omission rather than by
        // remembering to strip them.
        IReadOnlyDictionary<string, WishClaimRecord>? claims = null,
        // The caller's own gift status. Defaulted to null for the same reason the claims are: the
        // emergency reveal gets none by omission rather than by remembering to strip them.
        GiftStatus? gift = null) => new(
        member.MemberId, member.DisplayName, member.Wishlist, member.Avoidances, member.Address,
        wishes.Select(record => RecipientWishOf(record, claims)).ToList(),
        gift);
    private static RecipientWish RecipientWishOf(
        WishRecord record,
        IReadOnlyDictionary<string, WishClaimRecord>? claims) => new(
        record.WishId, record.Kind, record.Title,
        Empty(record.Url), Empty(record.ImageUrl), record.PriceCents,
        record.PriceCents is null ? null : Empty(record.Currency),
        record.Quantity, record.Priority, Empty(record.Details), record.Position,
        claims is not null && claims.TryGetValue(record.WishId, out var claim)
            ? new WishClaim(claim.State, claim.Quantity, claim.UpdatedAt)
            : null);
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
