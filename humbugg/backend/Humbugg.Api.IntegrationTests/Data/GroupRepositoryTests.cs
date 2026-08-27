using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Data;
using Humbugg.Api.Models;

using Xunit;

namespace Humbugg.Api.IntegrationTests.Data;

public sealed class GroupRepositoryTests(DevStackFixture stack) : DevStackTest(stack)
{
    private GroupRepository Repository => new(Db, Settings);

    private GroupRecord NewGroup(string groupId) => new(
        groupId, Uid("owner"), "Integration Exchange", "A test exchange",
        EventDate: "2026-12-24", SignupDeadline: null, SpendingLimitCents: 2500,
        Currency: "USD", Plan: PlanCode.Free, EntitlementId: null, Status: GroupStatus.Open,
        InviteHash: "hash", Exclusions: [["a", "b"]], CreatedAt: Now(), UpdatedAt: Now(),
        Customization: new ExchangeCustomization("Ho ho", "Wrap it", "#112233", "#445566"));

    private string TrackGroup()
    {
        var groupId = Uid("group");
        CleanupItem(Settings.GroupsTable, "group_id", groupId);
        CleanupItem(Settings.DrawsTable, "group_id", groupId);
        return groupId;
    }

    [IntegrationFact]
    public async Task Create_and_get_round_trip_the_full_record()
    {
        var groupId = TrackGroup();
        var group = NewGroup(groupId);

        await Repository.CreateAsync(group);
        var fetched = await Repository.GetAsync(groupId);

        Assert.NotNull(fetched);
        Assert.Equal(group.GroupId, fetched.GroupId);
        Assert.Equal(group.OwnerUserId, fetched.OwnerUserId);
        Assert.Equal("2026-12-24", fetched.EventDate);
        Assert.Null(fetched.SignupDeadline);          // stored as "", read back as null
        Assert.Null(fetched.EntitlementId);           // stored as NULL attribute
        Assert.Equal(2500, fetched.SpendingLimitCents);
        Assert.Equal(PlanCode.Free, fetched.Plan);
        Assert.Equal(GroupStatus.Open, fetched.Status);
        Assert.Equal([["a", "b"]], fetched.Exclusions);
        Assert.NotNull(fetched.Customization);
        Assert.Equal("Ho ho", fetched.Customization.Greeting);
        Assert.Equal("#112233", fetched.Customization.PrimaryColor);
    }

    [IntegrationFact]
    public async Task Create_refuses_an_existing_group_id()
    {
        var groupId = TrackGroup();
        await Repository.CreateAsync(NewGroup(groupId));
        await Assert.ThrowsAsync<ConditionalCheckFailedException>(() => Repository.CreateAsync(NewGroup(groupId)));
    }

    [IntegrationFact]
    public async Task Update_with_an_expected_status_guards_against_races()
    {
        var groupId = TrackGroup();
        await Repository.CreateAsync(NewGroup(groupId));

        var renamed = await Repository.UpdateAsync(groupId,
            new Dictionary<string, AttributeValue> { ["name"] = new("Renamed") }, GroupStatus.Open);
        Assert.Equal("Renamed", renamed.Name);

        await Assert.ThrowsAsync<ConditionalCheckFailedException>(() => Repository.UpdateAsync(groupId,
            new Dictionary<string, AttributeValue> { ["name"] = new("Too late") }, GroupStatus.Drawn));
    }

    [IntegrationFact]
    public async Task Draw_lifecycle_creates_reads_and_resets_transactionally()
    {
        var groupId = TrackGroup();
        await Repository.CreateAsync(NewGroup(groupId));
        var assignments = new Dictionary<string, string> { ["m1"] = "m2", ["m2"] = "m1" };

        await Repository.CreateDrawAsync(groupId, assignments, "actor-1");

        var group = await Repository.GetAsync(groupId);
        Assert.Equal(GroupStatus.Drawn, group!.Status);
        var draw = await Repository.GetDrawAsync(groupId);
        Assert.NotNull(draw);
        Assert.Equal(assignments, draw.Assignments);
        Assert.Equal("actor-1", draw.CreatedBy);

        // The group is no longer open, so a second draw must fail the whole transaction —
        // leaving the first draw untouched.
        await Assert.ThrowsAsync<TransactionCanceledException>(
            () => Repository.CreateDrawAsync(groupId, assignments, "actor-2"));

        await Repository.ResetDrawAsync(groupId);
        Assert.Equal(GroupStatus.Open, (await Repository.GetAsync(groupId))!.Status);
        Assert.Null(await Repository.GetDrawAsync(groupId));
    }

    [IntegrationFact]
    public async Task Late_proposal_saves_applies_and_reactivates_the_member()
    {
        var groupId = TrackGroup();
        await Repository.CreateAsync(NewGroup(groupId));
        await Repository.CreateDrawAsync(groupId, new Dictionary<string, string> { ["m1"] = "m2", ["m2"] = "m1" }, "actor");
        var draw = await Repository.GetDrawAsync(groupId);

        // The late member's row must exist and be non-participating for the apply transaction.
        var members = new MembershipRepository(Db, Settings);
        var lateUser = Uid("user");
        var member = await members.CreateAsync(groupId, lateUser, "Late Larry", organizer: false);
        Cleanup(() => members.DeleteAsync(member.MemberId));
        await members.UpdateParticipationAsync(member.MemberId, participating: false);

        var proposal = new LateParticipantProposalRecord(
            Uid("proposal"), member.MemberId, draw!.DrawId,
            new Dictionary<string, string> { ["m1"] = member.MemberId, [member.MemberId] = "m2", ["m2"] = "m1" },
            AffectedMemberIds: ["m1"], ExpiresAt: DateTimeOffset.UtcNow.AddMinutes(10).ToString("O"));

        await Repository.SaveLateProposalAsync(groupId, draw.DrawId, proposal);
        var savedProposal = (await Repository.GetDrawAsync(groupId))!.LateProposal;
        Assert.NotNull(savedProposal);
        // Record equality is reference equality for the collection members, so compare those
        // structurally and the scalars through the record.
        Assert.Equal(proposal.Assignments, savedProposal.Assignments);
        Assert.Equal(proposal.AffectedMemberIds, savedProposal.AffectedMemberIds);
        Assert.Equal(proposal with
        {
            Assignments = savedProposal.Assignments,
            AffectedMemberIds = savedProposal.AffectedMemberIds
        }, savedProposal);

        var newDrawId = await Repository.ApplyLateProposalAsync(groupId, draw.DrawId, proposal);
        var applied = await Repository.GetDrawAsync(groupId);
        Assert.Equal(newDrawId, applied!.DrawId);
        Assert.Null(applied.LateProposal);
        Assert.Equal(proposal.Assignments, applied.Assignments);
        Assert.Equal(["m1"], applied.LastAffectedMemberIds);
        Assert.True((await members.GetAsync(member.MemberId))!.IsParticipating);
    }

    [IntegrationFact]
    public async Task An_unsupported_stored_plan_fails_loudly_on_read()
    {
        var groupId = TrackGroup();
        var item = new Dictionary<string, AttributeValue>
        {
            ["group_id"] = new(groupId),
            ["owner_user_id"] = new("owner"),
            ["name"] = new("Corrupt"),
            ["description"] = new(""),
            ["plan"] = new("banana"),
            ["status"] = new("open"),
            ["invite_hash"] = new("h"),
            ["created_at"] = new(Now()),
            ["updated_at"] = new(Now())
        };
        await Db.PutItemAsync(new PutItemRequest { TableName = Settings.GroupsTable, Item = item });

        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => Repository.GetAsync(groupId));
        Assert.Contains("banana", error.Message);
    }
}
