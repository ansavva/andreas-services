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
    Task<GroupDetail> UpdateAsync(string groupId, UpdateGroupRequest request, CancellationToken cancellationToken = default);
    Task DeleteAsync(string groupId, CancellationToken cancellationToken = default);
    Task<InviteResponse> RotateInviteAsync(string groupId, CancellationToken cancellationToken = default);
    Task<GroupDetail> JoinAsync(string groupId, JoinGroupRequest request, CancellationToken cancellationToken = default);
    Task<Membership> GetMyMembershipAsync(string groupId, CancellationToken cancellationToken = default);
    Task<Membership> UpdateMyMembershipAsync(string groupId, UpdateMembershipRequest request, CancellationToken cancellationToken = default);
    Task LeaveAsync(string groupId, CancellationToken cancellationToken = default);
    Task<Membership> UpdateParticipationAsync(string groupId, string memberId, ParticipationRequest request, CancellationToken cancellationToken = default);
    Task<GroupDetail> SetExclusionsAsync(string groupId, ExclusionsRequest request, CancellationToken cancellationToken = default);
    Task<RecipientAssignment> DrawAsync(string groupId, CancellationToken cancellationToken = default);
    Task<GroupDetail> ResetAsync(string groupId, CancellationToken cancellationToken = default);
    Task<RecipientAssignment> GetAssignmentAsync(string groupId, CancellationToken cancellationToken = default);
    Task<RevealResponse> RevealAsync(string groupId, RevealRequest request, CancellationToken cancellationToken = default);
}

internal sealed class GroupService(
    ICurrentUser user,
    IProfileRepository profiles,
    IGroupRepository groups,
    IMembershipRepository memberships,
    IMatchingService matching,
    HumbuggSettings settings) : IGroupService
{
    private const int MaxMembers = 50;

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
        var secret = NewSecret();
        var now = DateTimeOffset.UtcNow.ToString("O");
        var dates = Validation.GroupDates(request.EventDate, request.SignupDeadline);
        var group = new GroupRecord(
            Guid.NewGuid().ToString(), user.UserId, Validation.Required(request.Name, "name", 120),
            Validation.Optional(request.Description, 1000), dates.EventDate,
            dates.SignupDeadline, Validation.SpendingLimit(request.SpendingLimit),
            "USD", GroupStatus.Open, Hash(secret), [], now, now);
        await groups.CreateAsync(group, cancellationToken);
        await memberships.CreateAsync(group.GroupId, user.UserId, profile.DisplayName, true, cancellationToken);
        var detail = await GetAsync(group.GroupId, cancellationToken);
        return detail with { InviteUrl = InviteUrl(group.GroupId, secret) };
    }

    public async Task<GroupDetail> GetAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var (group, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        var members = await memberships.GetByGroupAsync(groupId, cancellationToken);
        return Detail(group, membership, members);
    }

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
        if (fields.Count > 0) await groups.UpdateAsync(groupId, fields, cancellationToken: cancellationToken);
        return await GetAsync(groupId, cancellationToken);
    }

    public async Task DeleteAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var (_, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        RequireOrganizer(membership);
        await memberships.DeleteByGroupAsync(groupId, cancellationToken);
        await groups.DeleteAsync(groupId, cancellationToken);
    }

    public async Task<InviteResponse> RotateInviteAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var (group, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        RequireOrganizer(membership); RequireOpen(group);
        var secret = NewSecret();
        await ConditionalGroupUpdate(() => groups.UpdateAsync(groupId,
            new Dictionary<string, AttributeValue> { ["invite_hash"] = DynamoValues.S(Hash(secret)) }, GroupStatus.Open, cancellationToken));
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
        if ((await memberships.GetByGroupAsync(groupId, cancellationToken)).Count >= MaxMembers)
            throw ApiException.Conflict($"Groups support up to {MaxMembers} participants.");
        try { await memberships.CreateAsync(groupId, user.UserId, profile.DisplayName, false, cancellationToken); }
        catch (ConditionalCheckFailedException) { }
        return await GetAsync(groupId, cancellationToken);
    }

    public async Task<Membership> GetMyMembershipAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var (_, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        return Private(membership);
    }

    public async Task<Membership> UpdateMyMembershipAsync(string groupId, UpdateMembershipRequest request, CancellationToken cancellationToken = default)
    {
        var (_, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        var updated = await memberships.UpdatePrivateAsync(membership.MemberId,
            Validation.Optional(request.Wishlist ?? membership.Wishlist, 2000),
            Validation.Optional(request.Avoidances ?? membership.Avoidances, 2000),
            request.Address is null ? membership.Address : Validation.Address(request.Address), cancellationToken);
        return Private(updated);
    }

    public async Task LeaveAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var (group, membership) = await RequireMembershipAsync(groupId, cancellationToken); RequireOpen(group);
        if (membership.IsOrganizer) throw ApiException.Conflict("The organizer must delete the group instead of leaving it.");
        await memberships.DeleteAsync(membership.MemberId, cancellationToken);
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
        return Public(await memberships.UpdateParticipationAsync(memberId, request.IsParticipating.Value, cancellationToken));
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
        return await GetAsync(groupId, cancellationToken);
    }

    public async Task<RecipientAssignment> DrawAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var (group, actor) = await RequireMembershipAsync(groupId, cancellationToken); RequireOrganizer(actor); RequireOpen(group);
        var assignments = matching.CreateAssignments(
            (await memberships.GetByGroupAsync(groupId, cancellationToken)).Where(item => item.IsParticipating).Select(item => item.MemberId), group.Exclusions);
        try { await groups.CreateDrawAsync(groupId, assignments, user.UserId, cancellationToken); }
        catch (TransactionCanceledException) { throw ApiException.Conflict("This group has already been drawn or changed."); }
        return await GetAssignmentAsync(groupId, cancellationToken);
    }

    public async Task<GroupDetail> ResetAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var (group, actor) = await RequireMembershipAsync(groupId, cancellationToken); RequireOrganizer(actor);
        if (group.Status != GroupStatus.Drawn) throw ApiException.Conflict("This group has not been drawn.");
        try { await groups.ResetDrawAsync(groupId, cancellationToken); }
        catch (TransactionCanceledException) { throw ApiException.Conflict("The draw was already reset or changed."); }
        return await GetAsync(groupId, cancellationToken);
    }

    public async Task<RecipientAssignment> GetAssignmentAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var (group, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        if (group.Status != GroupStatus.Drawn) throw ApiException.Conflict("Assignments have not been created yet.");
        var draw = await groups.GetDrawAsync(groupId, cancellationToken);
        if (draw is null || !draw.Assignments.TryGetValue(membership.MemberId, out var recipientId))
            throw ApiException.NotFound("You do not have an assignment in this draw.");
        var recipient = await memberships.GetAsync(recipientId, cancellationToken)
            ?? throw ApiException.NotFound("Your assigned participant could not be found.");
        return Assignment(recipient);
    }

    public async Task<RevealResponse> RevealAsync(string groupId, RevealRequest request, CancellationToken cancellationToken = default)
    {
        var (group, actor) = await RequireMembershipAsync(groupId, cancellationToken); RequireOrganizer(actor);
        if (group.Status != GroupStatus.Drawn) throw ApiException.Conflict("Assignments have not been created yet.");
        var reason = Validation.Required(request.Reason, "reason", 500);
        var draw = await groups.GetDrawAsync(groupId, cancellationToken) ?? throw ApiException.NotFound("Draw record not found.");
        await groups.RecordRevealAsync(groupId, user.UserId, reason, cancellationToken);
        var members = (await memberships.GetByGroupAsync(groupId, cancellationToken)).ToDictionary(item => item.MemberId, StringComparer.Ordinal);
        var revealed = draw.Assignments.Where(pair => members.ContainsKey(pair.Key) && members.ContainsKey(pair.Value))
            .Select(pair => new RevealAssignment(Public(members[pair.Key]), Assignment(members[pair.Value]))).ToList();
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
    private static void RequireOpen(GroupRecord group) { if (group.Status != GroupStatus.Open) throw ApiException.Conflict("Reset the draw before changing the roster or matching rules."); }
    private static async Task ConditionalGroupUpdate(Func<Task<GroupRecord>> operation)
    {
        try { await operation(); } catch (ConditionalCheckFailedException) { throw ApiException.Conflict("This group has already been drawn or changed."); }
    }

    private GroupDetail Detail(GroupRecord group, MembershipRecord member, IReadOnlyList<MembershipRecord> all) => new(
        group.GroupId, group.Name, group.Status, group.EventDate, Amount(group.SpendingLimitCents), group.Currency,
        member.IsOrganizer, group.CreatedAt, group.UpdatedAt, group.Description, group.SignupDeadline,
        member.IsOrganizer ? group.Exclusions : [], all.Select(Public).ToList());
    private static GroupSummary Summary(GroupRecord group, MembershipRecord member) => new(
        group.GroupId, group.Name, group.Status, group.EventDate, Amount(group.SpendingLimitCents), group.Currency,
        member.IsOrganizer, group.CreatedAt, group.UpdatedAt);
    private static Membership Public(MembershipRecord member) => new(member.MemberId, member.DisplayName, member.IsOrganizer, member.IsParticipating);
    private static Membership Private(MembershipRecord member) => new(member.MemberId, member.DisplayName, member.IsOrganizer, member.IsParticipating, member.Wishlist, member.Avoidances, member.Address);
    private static RecipientAssignment Assignment(MembershipRecord member) => new(member.MemberId, member.DisplayName, member.Wishlist, member.Avoidances, member.Address);
    private static decimal? Amount(long? cents) => cents is null ? null : cents.Value / 100m;
    private static string NewSecret() => WebEncoders.Base64UrlEncode(RandomNumberGenerator.GetBytes(32));
    private static string Hash(string secret) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(secret))).ToLowerInvariant();
    private string InviteUrl(string groupId, string secret) => $"{settings.AppBaseUrl}/join/{groupId}#invite={secret}";
}
