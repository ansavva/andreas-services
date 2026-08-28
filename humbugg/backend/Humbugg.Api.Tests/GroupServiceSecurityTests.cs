using Amazon.DynamoDBv2.Model;
using Humbugg.Api;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class GroupServiceSecurityTests
{
    [Fact]
    public async Task NonMemberCannotReadGroup()
    {
        var fixture = new Fixture(member: null);
        var error = await Assert.ThrowsAsync<ApiException>(() => fixture.Subject.GetAsync("group", TestContext.Current.CancellationToken));
        Assert.Equal(403, error.StatusCode);
    }

    [Fact]
    public async Task OrdinaryMemberSeesNoExclusionsOrPrivateParticipantData()
    {
        var fixture = new Fixture(member: Fixture.Member("actor", organizer: false));
        fixture.Members.Items.Add(Fixture.Member("other", organizer: true) with
        {
            Wishlist = "private wish",
            Avoidances = "private avoidance",
            Address = new Address("private address")
        });

        var detail = await fixture.Subject.GetAsync("group", TestContext.Current.CancellationToken);

        Assert.Empty(detail.Exclusions);
        Assert.All(detail.Members, member =>
        {
            Assert.Null(member.Wishlist);
            Assert.Null(member.Avoidances);
            Assert.Null(member.Address);
        });
    }

    [Fact]
    public async Task NonOrganizerCannotRotateInvitation()
    {
        var fixture = new Fixture(member: Fixture.Member("actor", organizer: false));
        var error = await Assert.ThrowsAsync<ApiException>(() => fixture.Subject.RotateInviteAsync("group", TestContext.Current.CancellationToken));
        Assert.Equal(403, error.StatusCode);
        Assert.Equal(0, fixture.Groups.UpdateCount);
    }

    [Fact]
    public async Task OrdinaryMemberIsRejectedByEveryOrganizerEndpoint()
    {
        var fixture = new Fixture(member: Fixture.Member("actor", organizer: false));
        fixture.Members.Items.Add(Fixture.Member("other", organizer: false));
        var operations = new Func<Task>[]
        {
            () => fixture.Subject.UpdateAsync("group", new UpdateGroupRequest("New name", null, null, null, null), TestContext.Current.CancellationToken),
            () => fixture.Subject.RotateInviteAsync("group", TestContext.Current.CancellationToken),
            () => fixture.Subject.UpdateParticipationAsync("group", "other", new ParticipationRequest(false), TestContext.Current.CancellationToken),
            () => fixture.Subject.SetExclusionsAsync("group", new ExclusionsRequest([]), TestContext.Current.CancellationToken),
            () => fixture.Subject.DrawAsync("group", TestContext.Current.CancellationToken),
            () => fixture.Subject.ResetAsync("group", TestContext.Current.CancellationToken),
            () => fixture.Subject.DeleteAsync("group", TestContext.Current.CancellationToken),
            () => fixture.Subject.RevealAsync("group", new RevealRequest("reason"), TestContext.Current.CancellationToken)
        };

        foreach (var operation in operations)
        {
            var error = await Assert.ThrowsAsync<ApiException>(operation);
            Assert.Equal(403, error.StatusCode);
        }
    }

    [Fact]
    public async Task CoOrganizerCannotDeleteOrRevealAssignments()
    {
        var fixture = new Fixture(Fixture.Member("actor", organizer: true));

        var delete = await Assert.ThrowsAsync<ApiException>(() =>
            fixture.Subject.DeleteAsync("group", TestContext.Current.CancellationToken));
        var reveal = await Assert.ThrowsAsync<ApiException>(() =>
            fixture.Subject.RevealAsync("group", new RevealRequest("reason"), TestContext.Current.CancellationToken));

        Assert.Equal(403, delete.StatusCode);
        Assert.Equal(403, reveal.StatusCode);
    }

    [Fact]
    public async Task CoOrganizerCanUseEveryOrdinaryGroupManagementEndpoint()
    {
        var fixture = new Fixture(Fixture.Member("actor", organizer: true), exclusions: []);
        fixture.Members.Items.Add(Fixture.Member("other", organizer: false));

        await fixture.Subject.UpdateAsync(
            "group",
            new UpdateGroupRequest("Updated", null, null, null, null),
            TestContext.Current.CancellationToken);
        await fixture.Subject.RotateInviteAsync("group", TestContext.Current.CancellationToken);
        await fixture.Subject.UpdateParticipationAsync(
            "group",
            "other",
            new ParticipationRequest(false),
            TestContext.Current.CancellationToken);
        await fixture.Subject.UpdateParticipationAsync(
            "group",
            "other",
            new ParticipationRequest(true),
            TestContext.Current.CancellationToken);
        await fixture.Subject.SetExclusionsAsync(
            "group",
            new ExclusionsRequest([]),
            TestContext.Current.CancellationToken);
        await fixture.Subject.DrawAsync("group", TestContext.Current.CancellationToken);
        await fixture.Subject.ResetAsync("group", TestContext.Current.CancellationToken);

        Assert.Equal(3, fixture.Groups.UpdateCount);
        Assert.Equal(1, fixture.Groups.CreateDrawCount);
        Assert.Equal(1, fixture.Groups.ResetDrawCount);
    }

    [Fact]
    public async Task OwnerCanPromoteAndDemoteACoOrganizerAndChangesAreAudited()
    {
        var fixture = new Fixture(
            Fixture.Member("actor", organizer: true),
            ownerUserId: "user",
            plan: PlanCode.Plus,
            entitlementId: "plus:paid");
        fixture.Members.Items.Add(Fixture.Member("other", organizer: false));

        var promoted = await fixture.Subject.UpdateOrganizerRoleAsync(
            "group", "other", new OrganizerRoleRequest(true), TestContext.Current.CancellationToken);
        var demoted = await fixture.Subject.UpdateOrganizerRoleAsync(
            "group", "other", new OrganizerRoleRequest(false), TestContext.Current.CancellationToken);

        Assert.True(promoted.IsOrganizer);
        Assert.False(demoted.IsOrganizer);
        Assert.Equal([AuditAction.RoleChanged, AuditAction.RoleChanged], fixture.Audit.Actions);
    }

    [Fact]
    public async Task OwnerCannotRemoveTheirRequiredOwnership()
    {
        var fixture = new Fixture(
            Fixture.Member("actor", organizer: true),
            ownerUserId: "user",
            plan: PlanCode.Plus,
            entitlementId: "plus:paid");

        var error = await Assert.ThrowsAsync<ApiException>(() => fixture.Subject.UpdateOrganizerRoleAsync(
            "group", "actor", new OrganizerRoleRequest(false), TestContext.Current.CancellationToken));

        Assert.Equal(409, error.StatusCode);
        Assert.True(fixture.Members.Items.Single().IsOrganizer);
    }

    [Fact]
    public async Task ImpossibleDrawWritesNothing()
    {
        var organizer = Fixture.Member("actor", organizer: true);
        var fixture = new Fixture(organizer, exclusions: [["actor", "other"]]);
        fixture.Members.Items.Add(Fixture.Member("other", organizer: false));

        var error = await Assert.ThrowsAsync<ApiException>(() => fixture.Subject.DrawAsync("group", TestContext.Current.CancellationToken));

        Assert.Equal(409, error.StatusCode);
        Assert.Equal(0, fixture.Groups.CreateDrawCount);
    }

    [Fact]
    public async Task ServerRejectsReactivatingAMemberAtThePlanLimit()
    {
        var fixture = new Fixture(Fixture.Member("actor", organizer: true));
        for (var index = 1; index < 6; index++)
            fixture.Members.Items.Add(Fixture.Member($"active-{index}", organizer: false));
        fixture.Members.Items.Add(Fixture.Member("inactive", organizer: false) with { IsParticipating = false });

        var error = await Assert.ThrowsAsync<ApiException>(() => fixture.Subject.UpdateParticipationAsync(
            "group", "inactive", new ParticipationRequest(true), TestContext.Current.CancellationToken));

        Assert.Equal(402, error.StatusCode);
        Assert.Equal("plus_required", error.Code);
        Assert.Contains("Free plan", error.Message);
    }

    private sealed class Fixture
    {
        public FakeGroups Groups { get; }
        public FakeMembers Members { get; }
        public FakeAuditTrail Audit { get; }
        public GroupService Subject { get; }

        public Fixture(
            MembershipRecord? member,
            IReadOnlyList<string[]>? exclusions = null,
            string ownerUserId = "owner",
            PlanCode plan = PlanCode.Free,
            string? entitlementId = null)
        {
            Groups = new FakeGroups(Group(exclusions ?? [["actor", "other"]], ownerUserId, plan, entitlementId));
            Members = new FakeMembers(member is null ? [] : [member]);
            Audit = new FakeAuditTrail();
            Subject = new GroupService(new FakeUser(), new FakeProfiles(), Groups, Members, new FakeWishes(), new FakeInvitations(), new MatchingService(), new PlanCatalog(new()), Audit, new FakeProductAnalytics(), new HumbuggSettings(
                "us-east-1", "us-east-1", "pool", "client", ["http://localhost:5173"], "http://localhost:5173", null,
                "profiles", "groups", "members", "draws", "audit", "analytics"));
        }

        public static MembershipRecord Member(string memberId, bool organizer) => new(
            memberId, "group", memberId == "actor" ? "user" : $"user-{memberId}", memberId, organizer, true, "wish", "avoid", new Address("address"), "now", "now");

        private static GroupRecord Group(
            IReadOnlyList<string[]> exclusions,
            string ownerUserId,
            PlanCode plan,
            string? entitlementId) => new(
            "group", ownerUserId, "Exchange", "", null, null, null, "USD", plan, entitlementId, GroupStatus.Open, "hash", exclusions, "now", "now");
    }

    private sealed class FakeUser : ICurrentUser { public string UserId => "user"; }
    private sealed class FakeProfiles : IProfileRepository
    {
        public Task<ProfileRecord?> GetAsync(string userId, CancellationToken cancellationToken = default) => Task.FromResult<ProfileRecord?>(new(userId, "User", "now", "now"));
        public Task<ProfileRecord> UpsertAsync(string userId, string displayName, bool? nonEssentialEmailsEnabled = null, Consent? consent = null, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<ProfileRecord> SetAvatarKeyAsync(string userId, string? avatarKey, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string userId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class FakeGroups(GroupRecord group) : IGroupRepository
    {
        private GroupRecord group = group;
        private DrawRecord? draw;
        public int UpdateCount { get; private set; }
        public int CreateDrawCount { get; private set; }
        public int ResetDrawCount { get; private set; }
        public Task<GroupRecord?> GetAsync(string groupId, CancellationToken cancellationToken = default) => Task.FromResult<GroupRecord?>(group);
        public Task<GroupRecord> UpdateAsync(string groupId, IReadOnlyDictionary<string, AttributeValue> fields, GroupStatus? expectedStatus = null, CancellationToken cancellationToken = default) { UpdateCount++; return Task.FromResult(group); }
        public Task CreateDrawAsync(string groupId, IReadOnlyDictionary<string, string> assignments, string actorUserId, CancellationToken cancellationToken = default)
        {
            CreateDrawCount++;
            group = group with { Status = GroupStatus.Drawn };
            draw = new(groupId, "draw", assignments, "now", actorUserId);
            return Task.CompletedTask;
        }
        public Task<GroupRecord> CreateAsync(GroupRecord value, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<DrawRecord?> GetDrawAsync(string groupId, CancellationToken cancellationToken = default) => Task.FromResult(draw);
        public Task ResetDrawAsync(string groupId, CancellationToken cancellationToken = default)
        {
            ResetDrawCount++;
            group = group with { Status = GroupStatus.Open };
            draw = null;
            return Task.CompletedTask;
        }
    }

    private sealed class FakeAuditTrail : IAuditTrail
    {
        public List<AuditAction> Actions { get; } = [];
        public Task RecordAsync(AuditAction action, string groupId, AuditTarget target,
            IReadOnlyDictionary<string, string>? metadata = null, string? organizationId = null, CancellationToken cancellationToken = default)
        {
            Actions.Add(action);
            return Task.CompletedTask;
        }
    }

    private sealed class FakeProductAnalytics : IProductAnalytics
    {
        public Task TrackAsync(AnalyticsEventType type, PlanCode plan, string groupId, string idempotencyKey,
            IReadOnlyDictionary<string, string>? dimensions = null, CancellationToken cancellationToken = default) => Task.CompletedTask;
    }

    private sealed class FakeMembers(IEnumerable<MembershipRecord> items) : IMembershipRepository
    {
        public List<MembershipRecord> Items { get; } = items.ToList();
        // Real behaviour, not a counter: the readiness dashboard reads this field back, so a fake
        // that swallowed the write would let a test pass on a value production never stores.
        public Task MarkAssignmentViewedAsync(string memberId, string drawId, CancellationToken cancellationToken = default)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            if (index >= 0) Items[index] = Items[index] with { AssignmentViewedDrawId = drawId };
            return Task.CompletedTask;
        }
        public Task<MembershipRecord?> GetByUserAndGroupAsync(string userId, string groupId, CancellationToken cancellationToken = default) => Task.FromResult(Items.FirstOrDefault(item => item.UserId == userId && item.GroupId == groupId));
        public Task<IReadOnlyList<MembershipRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default) => Task.FromResult<IReadOnlyList<MembershipRecord>>(Items.Where(item => item.GroupId == groupId).ToList());
        public Task<IReadOnlyList<MembershipRecord>> GetByUserAsync(string userId, CancellationToken cancellationToken = default) => Task.FromResult<IReadOnlyList<MembershipRecord>>(Items.Where(item => item.UserId == userId).ToList());
        public Task<MembershipRecord?> GetAsync(string memberId, CancellationToken cancellationToken = default) => Task.FromResult(Items.FirstOrDefault(item => item.MemberId == memberId));
        public Task<MembershipRecord> CreateAsync(string groupId, string userId, string displayName, bool organizer, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdatePrivateAsync(string memberId, string wishlist, string avoidances, Address address, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdateParticipationAsync(string memberId, bool participating, CancellationToken cancellationToken = default)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            var updated = Items[index] with { IsParticipating = participating };
            Items[index] = updated;
            return Task.FromResult(updated);
        }
        public Task<MembershipRecord> UpdateOrganizerAsync(string memberId, bool organizer, CancellationToken cancellationToken = default)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            var updated = Items[index] with { IsOrganizer = organizer };
            Items[index] = updated;
            return Task.FromResult(updated);
        }
        public Task DeleteAsync(string memberId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task AnonymizeAsync(string memberId, string pseudonym, string displayName, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }
}
