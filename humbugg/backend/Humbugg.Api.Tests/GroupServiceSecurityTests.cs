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
        public GroupService Subject { get; }

        public Fixture(MembershipRecord? member, IReadOnlyList<string[]>? exclusions = null)
        {
            Groups = new FakeGroups(Group(exclusions ?? [["actor", "other"]]));
            Members = new FakeMembers(member is null ? [] : [member]);
            Subject = new GroupService(new FakeUser(), new FakeProfiles(), Groups, Members, new MatchingService(), new PlanCatalog(new()), new FakeAuditTrail(), new FakeProductAnalytics(), new HumbuggSettings(
                "us-east-1", "us-east-1", "pool", "client", "http://localhost:5173", "http://localhost:5173", null,
                "profiles", "groups", "members", "draws", "audit", "analytics"));
        }

        public static MembershipRecord Member(string memberId, bool organizer) => new(
            memberId, "group", memberId == "actor" ? "user" : $"user-{memberId}", memberId, organizer, true, "wish", "avoid", new Address("address"), "now", "now");

        private static GroupRecord Group(IReadOnlyList<string[]> exclusions) => new(
            "group", "owner", "Exchange", "", null, null, null, "USD", PlanCode.Free, null, GroupStatus.Open, "hash", exclusions, "now", "now");
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
        public int UpdateCount { get; private set; }
        public int CreateDrawCount { get; private set; }
        public Task<GroupRecord?> GetAsync(string groupId, CancellationToken cancellationToken = default) => Task.FromResult<GroupRecord?>(group);
        public Task<GroupRecord> UpdateAsync(string groupId, IReadOnlyDictionary<string, AttributeValue> fields, GroupStatus? expectedStatus = null, CancellationToken cancellationToken = default) { UpdateCount++; return Task.FromResult(group); }
        public Task CreateDrawAsync(string groupId, IReadOnlyDictionary<string, string> assignments, string actorUserId, CancellationToken cancellationToken = default) { CreateDrawCount++; return Task.CompletedTask; }
        public Task<GroupRecord> CreateAsync(GroupRecord value, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<DrawRecord?> GetDrawAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task ResetDrawAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class FakeAuditTrail : IAuditTrail
    {
        public Task RecordAsync(AuditAction action, string groupId, AuditTarget target,
            IReadOnlyDictionary<string, string>? metadata = null, string? organizationId = null, CancellationToken cancellationToken = default) => Task.CompletedTask;
    }

    private sealed class FakeProductAnalytics : IProductAnalytics
    {
        public Task TrackAsync(AnalyticsEventType type, PlanCode plan, string groupId, string idempotencyKey,
            IReadOnlyDictionary<string, string>? dimensions = null, CancellationToken cancellationToken = default) => Task.CompletedTask;
    }

    private sealed class FakeMembers(IEnumerable<MembershipRecord> items) : IMembershipRepository
    {
        public List<MembershipRecord> Items { get; } = items.ToList();
        public Task<MembershipRecord?> GetByUserAndGroupAsync(string userId, string groupId, CancellationToken cancellationToken = default) => Task.FromResult(Items.FirstOrDefault(item => item.UserId == userId && item.GroupId == groupId));
        public Task<IReadOnlyList<MembershipRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default) => Task.FromResult<IReadOnlyList<MembershipRecord>>(Items.Where(item => item.GroupId == groupId).ToList());
        public Task<IReadOnlyList<MembershipRecord>> GetByUserAsync(string userId, CancellationToken cancellationToken = default) => Task.FromResult<IReadOnlyList<MembershipRecord>>(Items.Where(item => item.UserId == userId).ToList());
        public Task<MembershipRecord?> GetAsync(string memberId, CancellationToken cancellationToken = default) => Task.FromResult(Items.FirstOrDefault(item => item.MemberId == memberId));
        public Task<MembershipRecord> CreateAsync(string groupId, string userId, string displayName, bool organizer, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdatePrivateAsync(string memberId, string wishlist, string avoidances, Address address, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdateParticipationAsync(string memberId, bool participating, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string memberId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task AnonymizeAsync(string memberId, string pseudonym, string displayName, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }
}
