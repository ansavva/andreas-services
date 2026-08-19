using Amazon.DynamoDBv2.Model;
using Humbugg.Api;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class AccountDeletionTests
{
    // ─── Product-profile data is erased ──────────────────────────────────────

    [Fact]
    public async Task DeletingAccountErasesTheProfile()
    {
        var world = new World();
        world.Profiles.Items["user"] = new ProfileRecord("user", "Alex", "now", "now");

        await world.Deletion.DeleteAsync(TestContext.Current.CancellationToken);

        Assert.False(world.Profiles.Items.ContainsKey("user"));
    }

    // ─── Organizer account deletion removes their whole group ────────────────

    [Fact]
    public async Task DeletingAccountDeletesGroupsTheUserOrganizes()
    {
        var world = new World();
        world.Groups.Add(Group("g-owned", GroupStatus.Open) with { OwnerUserId = "user" });
        world.Members.Items.Add(Member("g-owned", "user", organizer: true));
        world.Members.Items.Add(Member("g-owned", "other", organizer: false));

        await world.Deletion.DeleteAsync(TestContext.Current.CancellationToken);

        Assert.Contains("g-owned", world.Groups.Deleted);
        Assert.DoesNotContain(world.Members.Items, item => item.GroupId == "g-owned");
        Assert.Contains(world.Audit.Records, record => record.Action == AuditAction.GroupDeleted && record.GroupId == "g-owned");
    }

    // ─── Participant in an open group is removed and exclusions cleaned ──────

    [Fact]
    public async Task DeletingAccountRemovesParticipantMembershipAndCleansExclusions()
    {
        var world = new World();
        var me = Member("g-open", "user", organizer: false);
        world.Groups.Add(Group("g-open", GroupStatus.Open) with { Exclusions = [[me.MemberId, "member-x"]] });
        world.Members.Items.Add(me);
        world.Members.Items.Add(Member("g-open", "owner", organizer: true));

        await world.Deletion.DeleteAsync(TestContext.Current.CancellationToken);

        Assert.DoesNotContain(world.Members.Items, item => item.MemberId == me.MemberId);
        Assert.DoesNotContain("g-open", world.Groups.Deleted);
        Assert.Empty(world.Groups.Get("g-open").Exclusions);
        Assert.Contains(world.Audit.Records, record => record.Action == AuditAction.ParticipantRemoved && record.GroupId == "g-open");
    }

    // ─── Participant in a drawn group is anonymized, not deleted (draw integrity) ─

    [Fact]
    public async Task DeletingAccountAnonymizesParticipantInDrawnGroupToPreserveTheDraw()
    {
        var world = new World();
        var me = Member("g-drawn", "user", organizer: false) with { Wishlist = "a bike", Address = new Address("10 Downing St") };
        world.Groups.Add(Group("g-drawn", GroupStatus.Drawn));
        world.Members.Items.Add(me);

        await world.Deletion.DeleteAsync(TestContext.Current.CancellationToken);

        // The row survives (member_id unchanged) so a completed draw referencing it stays valid,
        // but every piece of personal data is gone and the user link is pseudonymized.
        var row = Assert.Single(world.Members.Items, item => item.MemberId == me.MemberId);
        Assert.Equal(AccountDeletionService.Pseudonym("user"), row.UserId);
        Assert.Equal("", row.Wishlist);
        Assert.Equal("", row.Avoidances);
        Assert.Equal(new Address(), row.Address);
        Assert.NotEqual("Alex", row.DisplayName);
        Assert.Contains(world.Audit.Records, record => record.Action == AuditAction.MembershipAnonymized && record.GroupId == "g-drawn");
    }

    // ─── Audit trail is preserved but the actor is anonymized ────────────────

    [Fact]
    public async Task DeletingAccountAnonymizesTheAuditActorAndRecordsATerminalEvent()
    {
        var world = new World();
        world.Profiles.Items["user"] = new ProfileRecord("user", "Alex", "now", "now");

        await world.Deletion.DeleteAsync(TestContext.Current.CancellationToken);

        var call = Assert.Single(world.Anonymizer.Calls);
        Assert.Equal("user", call.UserId);
        Assert.Equal(AccountDeletionService.Pseudonym("user"), call.Pseudonym);
        var terminal = Assert.Single(world.Audit.Records, record => record.Action == AuditAction.AccountDeleted);
        Assert.Equal("account", terminal.GroupId);
        Assert.Equal(AccountDeletionService.Pseudonym("user"), terminal.Target.Id);
    }

    // ─── Idempotent: a retried deletion is a clean no-op ─────────────────────

    [Fact]
    public async Task DeletingAccountIsIdempotent()
    {
        var world = new World();
        world.Profiles.Items["user"] = new ProfileRecord("user", "Alex", "now", "now");
        world.Groups.Add(Group("g-owned", GroupStatus.Open) with { OwnerUserId = "user" });
        world.Members.Items.Add(Member("g-owned", "user", organizer: true));

        await world.Deletion.DeleteAsync(TestContext.Current.CancellationToken);
        await world.Deletion.DeleteAsync(TestContext.Current.CancellationToken);

        // The second run found nothing to do: it did not throw, left no profile or membership behind,
        // and did not duplicate the terminal record. (Actor anonymization is deliberately re-run on
        // every attempt so a crash between the terminal write and anonymization still self-heals; it
        // is itself idempotent, so the repeated call is harmless.)
        Assert.Single(world.Audit.Records, record => record.Action == AuditAction.AccountDeleted);
        Assert.DoesNotContain(world.Members.Items, item => item.UserId == "user");
        Assert.False(world.Profiles.Items.ContainsKey("user"));
        Assert.All(world.Anonymizer.Calls, call => Assert.Equal(AccountDeletionService.Pseudonym("user"), call.Pseudonym));
    }

    // ─── A Work administrator cannot block a valid individual deletion ───────

    [Fact]
    public async Task WorkPlanMembershipDoesNotBlockDeletion()
    {
        var world = new World();
        world.Profiles.Items["user"] = new ProfileRecord("user", "Alex", "now", "now");
        // Deletion runs purely on the caller's own identity — there is no organization/admin gate to
        // consult — so a Work-plan group the person merely participates in is removed all the same.
        world.Groups.Add(Group("g-work", GroupStatus.Open) with { Plan = PlanCode.Work });
        var me = Member("g-work", "user", organizer: false);
        world.Members.Items.Add(me);
        world.Members.Items.Add(Member("g-work", "admin", organizer: true));

        await world.Deletion.DeleteAsync(TestContext.Current.CancellationToken);

        Assert.DoesNotContain(world.Members.Items, item => item.MemberId == me.MemberId);
    }

    [Fact]
    public void PseudonymIsDeterministicAndDoesNotLeakTheSubject()
    {
        Assert.Equal(AccountDeletionService.Pseudonym("user"), AccountDeletionService.Pseudonym("user"));
        Assert.NotEqual("user", AccountDeletionService.Pseudonym("user"));
        Assert.DoesNotContain("user", AccountDeletionService.Pseudonym("user")[13..]);
    }

    // ─── Participant self-service: clear my own wishlist and mailing address ─

    [Fact]
    public async Task ClearingMyPrivateDataErasesWishlistAvoidancesAndAddress()
    {
        var world = new World();
        world.Groups.Add(Group("g", GroupStatus.Open));
        world.Members.Items.Add(Member("g", "user", organizer: false) with
        {
            Wishlist = "a bike",
            Avoidances = "no socks",
            Address = new Address("10 Downing St", City: "London", PostalCode: "SW1", Country: "UK")
        });

        var cleared = await world.GroupService.ClearMyPrivateDataAsync("g", TestContext.Current.CancellationToken);

        Assert.Equal("", cleared.Wishlist);
        Assert.Equal("", cleared.Avoidances);
        Assert.Equal(new Address(), cleared.Address);
        Assert.Contains(world.Audit.Records, record => record.Action == AuditAction.ParticipantDataCleared);
    }

    [Fact]
    public async Task ClearingMyPrivateDataIsIdempotent()
    {
        var world = new World();
        world.Groups.Add(Group("g", GroupStatus.Open));
        world.Members.Items.Add(Member("g", "user", organizer: false) with { Wishlist = "a bike" });

        await world.GroupService.ClearMyPrivateDataAsync("g", TestContext.Current.CancellationToken);
        var second = await world.GroupService.ClearMyPrivateDataAsync("g", TestContext.Current.CancellationToken);

        Assert.Equal("", second.Wishlist);
    }

    // ─── Fakes / world ───────────────────────────────────────────────────────

    private static MembershipRecord Member(string groupId, string userId, bool organizer) => new(
        $"{groupId}:{userId}", groupId, userId, userId == "user" ? "Alex" : userId, organizer, true, "", "", new Address(), "now", "now");

    private static GroupRecord Group(string groupId, GroupStatus status) => new(
        groupId, "owner", "Exchange", "", null, null, null, "USD", PlanCode.Free, null, status, "hash", [], "now", "now");

    private sealed class World
    {
        public FakeUser User { get; } = new();
        public InMemoryProfiles Profiles { get; } = new();
        public InMemoryGroups Groups { get; } = new();
        public InMemoryMembers Members { get; } = new();
        public CapturingAudit Audit { get; } = new();
        public FakeAnonymizer Anonymizer { get; } = new();
        public AccountDeletionService Deletion { get; }
        public GroupService GroupService { get; }

        public World()
        {
            Deletion = new AccountDeletionService(User, Profiles, Groups, Members, Audit, Anonymizer);
            GroupService = new GroupService(User, Profiles, Groups, Members, new MatchingService(), new PlanCatalog(new()), Audit, new NoopAnalytics(),
                new HumbuggSettings("us-east-1", "us-east-1", "pool", "client", ["http://localhost:5173"], "http://localhost:5173", null,
                    "profiles", "groups", "members", "draws", "audit", "analytics"));
        }
    }

    private sealed class FakeUser : ICurrentUser { public string UserId => "user"; }

    private sealed class InMemoryProfiles : IProfileRepository
    {
        public Dictionary<string, ProfileRecord> Items { get; } = new(StringComparer.Ordinal);
        public Task<ProfileRecord?> GetAsync(string userId, CancellationToken cancellationToken = default) =>
            Task.FromResult(Items.TryGetValue(userId, out var record) ? record : null);
        public Task<ProfileRecord> UpsertAsync(string userId, string displayName, bool? nonEssentialEmailsEnabled = null, Consent? consent = null, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<ProfileRecord> SetAvatarKeyAsync(string userId, string? avatarKey, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string userId, CancellationToken cancellationToken = default) { Items.Remove(userId); return Task.CompletedTask; }
    }

    private sealed class InMemoryGroups : IGroupRepository
    {
        private readonly Dictionary<string, GroupRecord> groups = new(StringComparer.Ordinal);
        public List<string> Deleted { get; } = [];
        public void Add(GroupRecord group) => groups[group.GroupId] = group;
        public GroupRecord Get(string groupId) => groups[groupId];
        public Task<GroupRecord?> GetAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult(groups.TryGetValue(groupId, out var group) ? group : null);
        public Task<GroupRecord> UpdateAsync(string groupId, IReadOnlyDictionary<string, AttributeValue> fields, GroupStatus? expectedStatus = null, CancellationToken cancellationToken = default)
        {
            var group = groups[groupId];
            if (expectedStatus is not null && group.Status != expectedStatus.Value)
                throw new ConditionalCheckFailedException("status changed");
            if (fields.TryGetValue("exclusions", out var value) && value.L is not null)
                group = group with { Exclusions = value.L.Select(pair => pair.L!.Select(entry => entry.S).ToArray()).ToList() };
            groups[groupId] = group;
            return Task.FromResult(group);
        }
        public Task DeleteAsync(string groupId, CancellationToken cancellationToken = default) { groups.Remove(groupId); Deleted.Add(groupId); return Task.CompletedTask; }
        public Task<GroupRecord> CreateAsync(GroupRecord group, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task CreateDrawAsync(string groupId, IReadOnlyDictionary<string, string> assignments, string actorUserId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<DrawRecord?> GetDrawAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task ResetDrawAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class InMemoryMembers : IMembershipRepository
    {
        public List<MembershipRecord> Items { get; } = [];
        public Task<MembershipRecord?> GetAsync(string memberId, CancellationToken cancellationToken = default) =>
            Task.FromResult(Items.FirstOrDefault(item => item.MemberId == memberId));
        public Task<IReadOnlyList<MembershipRecord>> GetByUserAsync(string userId, CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<MembershipRecord>>(Items.Where(item => item.UserId == userId).ToList());
        public Task<IReadOnlyList<MembershipRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<MembershipRecord>>(Items.Where(item => item.GroupId == groupId).ToList());
        public Task<MembershipRecord?> GetByUserAndGroupAsync(string userId, string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult(Items.FirstOrDefault(item => item.UserId == userId && item.GroupId == groupId));
        public Task<MembershipRecord> UpdatePrivateAsync(string memberId, string wishlist, string avoidances, Address address, CancellationToken cancellationToken = default)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            Items[index] = Items[index] with { Wishlist = wishlist, Avoidances = avoidances, Address = address };
            return Task.FromResult(Items[index]);
        }
        public Task AnonymizeAsync(string memberId, string pseudonym, string displayName, CancellationToken cancellationToken = default)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            Items[index] = Items[index] with { UserId = pseudonym, DisplayName = displayName, Wishlist = "", Avoidances = "", Address = new Address() };
            return Task.CompletedTask;
        }
        public Task DeleteAsync(string memberId, CancellationToken cancellationToken = default) { Items.RemoveAll(item => item.MemberId == memberId); return Task.CompletedTask; }
        public Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default) { Items.RemoveAll(item => item.GroupId == groupId); return Task.CompletedTask; }
        public Task<MembershipRecord> CreateAsync(string groupId, string userId, string displayName, bool organizer, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdateParticipationAsync(string memberId, bool participating, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed record AuditRecord(AuditAction Action, string GroupId, AuditTarget Target);

    private sealed class CapturingAudit : IAuditTrail
    {
        public List<AuditRecord> Records { get; } = [];
        public Task RecordAsync(AuditAction action, string groupId, AuditTarget target,
            IReadOnlyDictionary<string, string>? metadata = null, string? organizationId = null, CancellationToken cancellationToken = default)
        {
            Records.Add(new AuditRecord(action, groupId, target));
            return Task.CompletedTask;
        }
    }

    private sealed class FakeAnonymizer : IAuditActorAnonymizer
    {
        public List<(string UserId, string Pseudonym)> Calls { get; } = [];
        public Task<int> AnonymizeActorAsync(string userId, string pseudonym, CancellationToken cancellationToken = default)
        {
            Calls.Add((userId, pseudonym));
            return Task.FromResult(0);
        }
    }

    private sealed class NoopAnalytics : IProductAnalytics
    {
        public Task TrackAsync(AnalyticsEventType type, PlanCode plan, string groupId, string idempotencyKey,
            IReadOnlyDictionary<string, string>? dimensions = null, CancellationToken cancellationToken = default) => Task.CompletedTask;
    }
}
