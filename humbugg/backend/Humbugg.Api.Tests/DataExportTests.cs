using System.Text.Json;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class DataExportTests
{
    // ─── The caller's own profile and authored content are exported ──────────

    [Fact]
    public async Task ExportsTheCallersProfileAndEmail()
    {
        var world = new World();
        world.Profiles.Items["user"] = new ProfileRecord("user", "Alex", "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z");

        var export = await world.Service.ExportAsync(TestContext.Current.CancellationToken);

        Assert.Equal("user", export.Profile.UserId);
        Assert.Equal("Alex", export.Profile.DisplayName);
        Assert.Equal("alex@example.com", export.Profile.Email);
        Assert.Equal("2026-01-01T00:00:00Z", export.Profile.CreatedAt);
        Assert.Equal("user", export.Metadata.SubjectUserId);
        Assert.Equal("1.0", export.Metadata.FormatVersion);
    }

    [Fact]
    public async Task ExportsTheWishlistAvoidancesAndAddressTheCallerAuthored()
    {
        var world = new World();
        world.Groups.Add(Group("g1", "Family Exchange", GroupStatus.Open));
        world.Members.Add(Member("g1", "user", organizer: false) with
        {
            Wishlist = "a warm scarf",
            Avoidances = "no chocolate",
            Address = new Address("10 Downing St", City: "London", PostalCode: "SW1", Country: "UK"),
        });

        var export = await world.Service.ExportAsync(TestContext.Current.CancellationToken);

        var membership = Assert.Single(export.Memberships);
        Assert.Equal("g1", membership.GroupId);
        Assert.Equal("Family Exchange", membership.GroupName);
        Assert.Equal("participant", membership.Role);
        Assert.Equal("a warm scarf", membership.Wishlist);
        Assert.Equal("no chocolate", membership.Avoidances);
        Assert.Equal("London", membership.Address?.City);
    }

    [Fact]
    public async Task CoOrganizerRoleIsReflectedInTheExport()
    {
        var world = new World();
        world.Groups.Add(Group("g1", "Office Party", GroupStatus.Open));
        world.Members.Add(Member("g1", "user", organizer: true));

        var export = await world.Service.ExportAsync(TestContext.Current.CancellationToken);

        Assert.Equal("co_organizer", Assert.Single(export.Memberships).Role);
    }

    // ─── The export never leaks anyone else's personal data ──────────────────

    [Fact]
    public async Task ExcludesOtherMembersMembershipsAndPii()
    {
        var world = new World();
        world.Groups.Add(Group("g1", "Family Exchange", GroupStatus.Drawn));
        world.Members.Add(Member("g1", "user", organizer: false) with { Wishlist = "a warm scarf" });
        // Another member in the SAME group with their own secret data + a completed assignment.
        world.Members.Add(Member("g1", "santa", organizer: true) with
        {
            Wishlist = "SECRET-SANTA-WISHLIST",
            Avoidances = "SECRET-SANTA-AVOIDANCE",
            Address = new Address("SECRET-SANTA-STREET", City: "Nowhere", PostalCode: "ZZ1", Country: "UK"),
        });

        var export = await world.Service.ExportAsync(TestContext.Current.CancellationToken);

        // Only the caller's own membership is present.
        var membership = Assert.Single(export.Memberships);
        Assert.Equal($"g1:user", membership.MemberId);

        // Nothing that belongs to another member appears anywhere in the serialized document —
        // in particular no other member's wishlist/address and no draw/assignment/recipient data.
        var json = JsonSerializer.Serialize(export);
        Assert.DoesNotContain("SECRET-SANTA-WISHLIST", json, StringComparison.Ordinal);
        Assert.DoesNotContain("SECRET-SANTA-AVOIDANCE", json, StringComparison.Ordinal);
        Assert.DoesNotContain("SECRET-SANTA-STREET", json, StringComparison.Ordinal);
        Assert.DoesNotContain("santa", json, StringComparison.Ordinal);
    }

    // ─── Email absent from the token is omitted with an explanatory note ─────

    [Fact]
    public async Task OmitsEmailWhenTheTokenDoesNotCarryIt()
    {
        var world = new World { User = { Email = null } };
        world.Profiles.Items["user"] = new ProfileRecord("user", "Alex", "now", "now");

        var export = await world.Service.ExportAsync(TestContext.Current.CancellationToken);

        Assert.Null(export.Profile.Email);
        Assert.Contains(export.Metadata.Notes, note => note.Contains("Cognito", StringComparison.Ordinal));
    }

    // ─── Reserved fields for in-flight work are present but null with a note ─

    [Fact]
    public async Task ReservedFieldsForInFlightWorkAreNullWithNotes()
    {
        var world = new World();
        world.Profiles.Items["user"] = new ProfileRecord("user", "Alex", "now", "now");

        var export = await world.Service.ExportAsync(TestContext.Current.CancellationToken);

        Assert.Null(export.Profile.Avatar);
        Assert.Null(export.Profile.NonEssentialEmailsEnabled);
        Assert.Null(export.Profile.Consent);
        Assert.Contains(export.Metadata.Notes, note => note.Contains("#186", StringComparison.Ordinal));
        Assert.Contains(export.Metadata.Notes, note => note.Contains("#187", StringComparison.Ordinal));
        Assert.Contains(export.Metadata.Notes, note => note.Contains("#188", StringComparison.Ordinal));
    }

    // ─── Read-only: safe to call repeatedly with an identical result shape ───

    [Fact]
    public async Task IsSafeToCallRepeatedly()
    {
        var world = new World();
        world.Profiles.Items["user"] = new ProfileRecord("user", "Alex", "now", "now");
        world.Groups.Add(Group("g1", "Exchange", GroupStatus.Open));
        world.Members.Add(Member("g1", "user", organizer: false) with { Wishlist = "a bike" });

        var first = await world.Service.ExportAsync(TestContext.Current.CancellationToken);
        var second = await world.Service.ExportAsync(TestContext.Current.CancellationToken);

        Assert.Equal(first.Profile.DisplayName, second.Profile.DisplayName);
        Assert.Equal(first.Memberships.Count, second.Memberships.Count);
        Assert.Single(second.Memberships);
    }

    [Fact]
    public async Task SkipsMembershipsWhoseGroupIsAlreadyGone()
    {
        var world = new World();
        world.Members.Add(Member("ghost", "user", organizer: false)); // no matching group added

        var export = await world.Service.ExportAsync(TestContext.Current.CancellationToken);

        Assert.Empty(export.Memberships);
    }

    // ─── Fakes / world ───────────────────────────────────────────────────────

    private static MembershipRecord Member(string groupId, string userId, bool organizer) => new(
        $"{groupId}:{userId}", groupId, userId, userId == "user" ? "Alex" : userId, organizer, true, "", "", new Address(), "now", "now");

    private static GroupRecord Group(string groupId, string name, GroupStatus status) => new(
        groupId, "owner", name, "", null, null, null, "USD", PlanCode.Free, null, status, "hash", [], "now", "now");

    private sealed class World
    {
        public FakeUser User { get; } = new();
        public InMemoryProfiles Profiles { get; } = new();
        public InMemoryGroups Groups { get; } = new();
        public InMemoryMembers Members { get; } = new();
        public DataExportService Service { get; }

        public World() => Service = new DataExportService(User, Profiles, Groups, Members);
    }

    private sealed class FakeUser : ICurrentUser
    {
        public string UserId => "user";
        public string? Email { get; set; } = "alex@example.com";
    }

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
        public void Add(GroupRecord group) => groups[group.GroupId] = group;
        public Task<GroupRecord?> GetAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult(groups.TryGetValue(groupId, out var group) ? group : null);
        public Task<GroupRecord> UpdateAsync(string groupId, IReadOnlyDictionary<string, Amazon.DynamoDBv2.Model.AttributeValue> fields, GroupStatus? expectedStatus = null, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<GroupRecord> CreateAsync(GroupRecord group, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task CreateDrawAsync(string groupId, IReadOnlyDictionary<string, string> assignments, string actorUserId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<DrawRecord?> GetDrawAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task ResetDrawAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class InMemoryMembers : IMembershipRepository
    {
        private readonly List<MembershipRecord> items = [];
        public void Add(MembershipRecord member) => items.Add(member);
        public Task<MembershipRecord?> GetAsync(string memberId, CancellationToken cancellationToken = default) =>
            Task.FromResult(items.FirstOrDefault(item => item.MemberId == memberId));
        public Task<IReadOnlyList<MembershipRecord>> GetByUserAsync(string userId, CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<MembershipRecord>>(items.Where(item => item.UserId == userId).ToList());
        public Task<IReadOnlyList<MembershipRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<MembershipRecord>>(items.Where(item => item.GroupId == groupId).ToList());
        public Task<MembershipRecord?> GetByUserAndGroupAsync(string userId, string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult(items.FirstOrDefault(item => item.UserId == userId && item.GroupId == groupId));
        public Task<MembershipRecord> CreateAsync(string groupId, string userId, string displayName, bool organizer, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdatePrivateAsync(string memberId, string wishlist, string avoidances, Address address, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdateParticipationAsync(string memberId, bool participating, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task AnonymizeAsync(string memberId, string pseudonym, string displayName, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string memberId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }
}
