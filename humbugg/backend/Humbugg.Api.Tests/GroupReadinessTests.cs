using Amazon.DynamoDBv2.Model;
using Humbugg.Api;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Xunit;

namespace Humbugg.Api.Tests;

/// <summary>
/// The organizer readiness dashboard (#133). Two things are under test: that the states mean what
/// the dashboard says they mean, and that computing them leaks nothing — an organizer learns that a
/// list is empty, never what is on it, and never who was drawn for whom.
/// </summary>
public sealed class GroupReadinessTests
{
    [Fact]
    public async Task OrdinaryMemberCannotOpenTheDashboard()
    {
        var fixture = new Fixture(organizer: false);

        var error = await Assert.ThrowsAsync<ApiException>(() =>
            fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken));

        Assert.Equal(403, error.StatusCode);
    }

    [Fact]
    public async Task NonMemberCannotOpenTheDashboard()
    {
        var fixture = new Fixture(actor: null);

        var error = await Assert.ThrowsAsync<ApiException>(() =>
            fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken));

        Assert.Equal(403, error.StatusCode);
    }

    [Fact]
    public async Task ACoOrganizerSeesTheSameDashboardAsTheOwner()
    {
        var fixture = new Fixture(ownerUserId: "someone-else");

        var readiness = await fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken);

        Assert.Equal(ParticipantRole.CoOrganizer, readiness.Participants.Single(p => p.MemberId == "actor").Role);
    }

    [Fact]
    public async Task TheDashboardIsNotGatedOnAPlan()
    {
        foreach (var plan in new[] { PlanCode.Free, PlanCode.Plus, PlanCode.Work })
        {
            var fixture = new Fixture(plan: plan, entitlementId: plan == PlanCode.Free ? null : $"{plan}:paid".ToLowerInvariant());

            var readiness = await fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken);

            Assert.Equal(plan, readiness.Plan);
        }
    }

    [Fact]
    public async Task AWishlistIsReadyOnStructuredWishesAloneAndOnFreeTextAlone()
    {
        var fixture = new Fixture();
        fixture.Members.Items.Add(Fixture.Member("wishes-only", wishlist: ""));
        fixture.Members.Items.Add(Fixture.Member("text-only", wishlist: "Socks, please"));
        fixture.Members.Items.Add(Fixture.Member("neither", wishlist: ""));
        fixture.Wishes = new FakeWishes(FakeWishes.Record("wishes-only", "wish-1"));

        var readiness = await fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken);

        Assert.Equal(ReadinessState.Ready, Participant(readiness, "wishes-only").Wishlist);
        Assert.Equal(ReadinessState.Ready, Participant(readiness, "text-only").Wishlist);
        Assert.Equal(ReadinessState.Missing, Participant(readiness, "neither").Wishlist);
        Assert.Equal(1, Participant(readiness, "wishes-only").WishCount);
        Assert.Equal(0, Participant(readiness, "text-only").WishCount);
    }

    [Fact]
    public async Task AMissingAddressIsNotHeldAgainstAnExchangeThatDoesNotPostItsGifts()
    {
        var fixture = new Fixture(requiresAddress: false);
        fixture.Members.Items.Add(Fixture.Member("no-address", address: new Address()));

        var readiness = await fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken);

        Assert.Equal(ReadinessState.NotRequired, Participant(readiness, "no-address").Address);
        Assert.Empty(Participant(readiness, "no-address").Nudges);
        Assert.Equal(0, readiness.Counts.AddressReady);
    }

    [Fact]
    public async Task AnExchangeThatPostsItsGiftsCountsAMissingAddress()
    {
        var fixture = new Fixture(requiresAddress: true);
        fixture.Members.Items.Add(Fixture.Member("no-address", address: new Address()));
        fixture.Members.Items.Add(Fixture.Member("half-address", address: new Address("12 Elm Street")));

        var readiness = await fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken);

        Assert.True(readiness.RequiresAddress);
        Assert.Equal(ReadinessState.Ready, Participant(readiness, "actor").Address);
        Assert.Equal(ReadinessState.Missing, Participant(readiness, "no-address").Address);
        // A partial address is not an address: the write path rejects one, and a row carrying only a
        // street line would otherwise report ready and post nowhere.
        Assert.Equal(ReadinessState.Missing, Participant(readiness, "half-address").Address);
        Assert.Contains(NudgeReason.NoAddress, Participant(readiness, "no-address").Nudges);
    }

    [Fact]
    public async Task NothingIsAskedOfSomeoneWhoIsNotParticipating()
    {
        var fixture = new Fixture(requiresAddress: true);
        fixture.Members.Items.Add(Fixture.Member("sitting-out", wishlist: "", address: new Address()) with { IsParticipating = false });

        var readiness = await fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken);
        var member = Participant(readiness, "sitting-out");

        Assert.Equal(ReadinessState.NotApplicable, member.Wishlist);
        Assert.Equal(ReadinessState.NotApplicable, member.Address);
        Assert.Equal(ReadinessState.NotApplicable, member.Assignment);
        Assert.Empty(member.Nudges);
        Assert.Equal(1, readiness.Counts.NotParticipating);
        Assert.Equal(0, readiness.Counts.NeedsNudge);
    }

    [Fact]
    public async Task AssignmentViewsAreNotAskedAboutBeforeTheDraw()
    {
        var fixture = new Fixture();

        var readiness = await fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken);

        Assert.Equal(GroupStatus.Open, readiness.Status);
        Assert.Equal(ReadinessState.NotApplicable, Participant(readiness, "actor").Assignment);
        Assert.Equal(0, readiness.Counts.AssignmentsViewed);
    }

    [Fact]
    public async Task ReadingAnAssignmentIsWhatMarksItViewed()
    {
        var fixture = new Fixture();
        fixture.Members.Items.Add(Fixture.Member("other"));
        await fixture.Subject.DrawAsync("group", TestContext.Current.CancellationToken);

        // DrawAsync returns the drawing organizer's own assignment, so "actor" has already looked.
        var afterDraw = await fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken);
        Assert.Equal(ReadinessState.Ready, Participant(afterDraw, "actor").Assignment);
        Assert.Equal(ReadinessState.Missing, Participant(afterDraw, "other").Assignment);
        Assert.Contains(NudgeReason.AssignmentNotViewed, Participant(afterDraw, "other").Nudges);

        fixture.User.UserId = "user-other";
        await fixture.Subject.GetAssignmentAsync("group", TestContext.Current.CancellationToken);
        fixture.User.UserId = "user";

        var afterLooking = await fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken);
        Assert.Equal(ReadinessState.Ready, Participant(afterLooking, "other").Assignment);
        Assert.Equal(2, afterLooking.Counts.AssignmentsViewed);
    }

    [Fact]
    public async Task ARereadDoesNotRewriteTheMarker()
    {
        var fixture = new Fixture();
        fixture.Members.Items.Add(Fixture.Member("other"));
        await fixture.Subject.DrawAsync("group", TestContext.Current.CancellationToken);
        var afterDraw = fixture.Members.MarkAssignmentViewedCalls;

        await fixture.Subject.GetAssignmentAsync("group", TestContext.Current.CancellationToken);
        await fixture.Subject.GetAssignmentAsync("group", TestContext.Current.CancellationToken);

        Assert.Equal(1, afterDraw);
        Assert.Equal(afterDraw, fixture.Members.MarkAssignmentViewedCalls);
    }

    [Fact]
    public async Task ResettingTheDrawTakesEveryoneBackToNotHavingLooked()
    {
        var fixture = new Fixture();
        fixture.Members.Items.Add(Fixture.Member("other"));
        await fixture.Subject.DrawAsync("group", TestContext.Current.CancellationToken);
        await fixture.Subject.ResetAsync("group", TestContext.Current.CancellationToken);
        await fixture.Subject.DrawAsync("group", TestContext.Current.CancellationToken);

        // The second draw has its own id, so the marker left by the first no longer matches — except
        // for the organizer, whose own DrawAsync call re-read the assignment and re-marked it.
        var readiness = await fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken);

        Assert.Equal(ReadinessState.Ready, Participant(readiness, "actor").Assignment);
        Assert.Equal(ReadinessState.Missing, Participant(readiness, "other").Assignment);
    }

    [Fact]
    public async Task UnacceptedInvitationsAreTheOtherHalfOfTheNudgeList()
    {
        var fixture = new Fixture();
        fixture.Invitations.Items.Add(FakeInvitations.Pending("i-1", "group", "zoe@example.com", "msg-1"));
        fixture.Invitations.Items.Add(FakeInvitations.Pending("i-2", "group", "adam@example.com", "msg-2"));
        fixture.Invitations.Items.Add(FakeInvitations.Pending("i-3", "group", "joined@example.com") with { Status = "accepted" });
        fixture.Invitations.Items.Add(FakeInvitations.Pending("i-4", "group", "withdrawn@example.com") with { Status = "revoked" });
        fixture.Invitations.Items.Add(FakeInvitations.Pending("i-5", "group", "stale@example.com") with
        {
            ExpiresAt = DateTimeOffset.UtcNow.AddDays(-1).ToString("O")
        });
        fixture.Invitations.DeliveryStatuses["msg-2"] = "bounce";

        var readiness = await fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken);

        Assert.Equal(["adam@example.com", "zoe@example.com"], readiness.PendingInvitations.Select(item => item.Email));
        // The bounce is the point: an address that never arrived is exactly who an organizer chases.
        Assert.Equal(InvitationStatus.Bounced, readiness.PendingInvitations[0].Status);
        Assert.Equal(InvitationStatus.Sent, readiness.PendingInvitations[1].Status);
        Assert.Equal(2, readiness.Counts.PendingInvitations);
        Assert.Equal(2, readiness.Counts.NeedsNudge);
    }

    [Fact]
    public async Task AFreeExchangeInvitingByLinkHasNoPendingInvitationsAndSaysSo()
    {
        var fixture = new Fixture(plan: PlanCode.Free);

        var readiness = await fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken);

        Assert.Empty(readiness.PendingInvitations);
        Assert.Equal(0, readiness.Counts.PendingInvitations);
    }

    [Fact]
    public async Task CountsAddUpAcrossAMixedRoster()
    {
        var fixture = new Fixture(requiresAddress: true);
        fixture.Members.Items.Add(Fixture.Member("ready"));
        fixture.Members.Items.Add(Fixture.Member("no-list", wishlist: ""));
        fixture.Members.Items.Add(Fixture.Member("no-address", address: new Address()));
        fixture.Members.Items.Add(Fixture.Member("neither", wishlist: "", address: new Address()));
        fixture.Members.Items.Add(Fixture.Member("sitting-out", wishlist: "", address: new Address()) with { IsParticipating = false });
        fixture.Invitations.Items.Add(FakeInvitations.Pending("i-1", "group", "pending@example.com"));

        var readiness = await fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken);

        Assert.Equal(6, readiness.Counts.Members);
        Assert.Equal(5, readiness.Counts.Participating);
        Assert.Equal(1, readiness.Counts.NotParticipating);
        // actor, "ready" and "no-address" have lists; "no-list" and "neither" do not.
        Assert.Equal(3, readiness.Counts.WishlistReady);
        // actor, "ready" and "no-list" have addresses.
        Assert.Equal(3, readiness.Counts.AddressReady);
        // "no-list", "no-address" and "neither" — "neither" is one person needing a nudge, not two.
        Assert.Equal(4, readiness.Counts.NeedsNudge);
        Assert.Equal([NudgeReason.NoWishlist, NudgeReason.NoAddress], Participant(readiness, "neither").Nudges);
    }

    [Fact]
    public async Task TheOwnerIsNamedAsTheOwnerAndTheRestByWhatTheyAre()
    {
        var fixture = new Fixture();
        fixture.Members.Items.Add(Fixture.Member("deputy") with { IsOrganizer = true });
        fixture.Members.Items.Add(Fixture.Member("guest"));

        var readiness = await fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken);

        Assert.Equal(ParticipantRole.Owner, Participant(readiness, "actor").Role);
        Assert.Equal(ParticipantRole.CoOrganizer, Participant(readiness, "deputy").Role);
        Assert.Equal(ParticipantRole.Participant, Participant(readiness, "guest").Role);
    }

    [Fact]
    public async Task ParticipantsComeBackInNameOrderSoALongRosterIsScannable()
    {
        var fixture = new Fixture();
        foreach (var name in new[] { "zoe", "Adam", "mia" })
            fixture.Members.Items.Add(Fixture.Member(name));

        var readiness = await fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken);

        Assert.Equal(["actor", "Adam", "mia", "zoe"], readiness.Participants.Select(item => item.DisplayName));
    }

    [Fact]
    public async Task TheDashboardCarriesNoWishlistAddressOrAssignmentContent()
    {
        var fixture = new Fixture(requiresAddress: true);
        fixture.Members.Items.Add(Fixture.Member("other", wishlist: "a signed first edition", address: new Address(
            "22 Secret Lane", "", "Springfield", "IL", "62704", "US")));
        fixture.Wishes = new FakeWishes(FakeWishes.Record("other", "wish-1", title: "a signed first edition"));
        await fixture.Subject.DrawAsync("group", TestContext.Current.CancellationToken);

        var readiness = await fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken);
        var rendered = System.Text.Json.JsonSerializer.Serialize(readiness);

        Assert.DoesNotContain("signed first edition", rendered, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Secret Lane", rendered, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("62704", rendered, StringComparison.Ordinal);
        // The draw pairs everyone with someone; the dashboard must not be able to say who.
        Assert.DoesNotContain("recipient", rendered, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task GiftProgressIsAbsentRatherThanZeroUntilGiftTrackingExists()
    {
        var fixture = new Fixture();
        fixture.Members.Items.Add(Fixture.Member("other"));
        await fixture.Subject.DrawAsync("group", TestContext.Current.CancellationToken);

        var readiness = await fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken);

        // #132 fills this in. Null is "not tracked"; a zeroed record would be "nobody has bought
        // anything", which is a claim this codebase currently has no way to make.
        Assert.Null(readiness.GiftProgress);
    }

    [Fact]
    public async Task AWishCountIsFetchedOnlyForPeopleWhoAreParticipating()
    {
        var fixture = new Fixture();
        fixture.Members.Items.Add(Fixture.Member("sitting-out") with { IsParticipating = false });
        var counting = new CountingWishes();
        fixture.Wishes = counting;

        await fixture.Subject.GetReadinessAsync("group", TestContext.Current.CancellationToken);

        Assert.Equal(["actor"], counting.QueriedMembers);
    }

    private static ParticipantReadiness Participant(GroupReadiness readiness, string memberId) =>
        readiness.Participants.Single(item => item.MemberId == memberId);

    private sealed class Fixture
    {
        private readonly FakeUser user = new();
        private GroupService? subject;

        public FakeGroups Groups { get; }
        public RecordingMembers Members { get; }
        public FakeInvitations Invitations { get; } = new();
        public IWishRepository Wishes { get; set; } = new FakeWishes();
        public FakeUser User => user;

        // Built lazily so a test can swap the wish repository in after seeding its roster.
        public GroupService Subject => subject ??= new GroupService(
            user, new FakeProfiles(), Groups, Members, Wishes, Invitations, new MatchingService(),
            new PlanCatalog(new()), new NoopAudit(), new NoopAnalytics(),
            new HumbuggSettings("us-east-1", "us-east-1", "pool", "client", ["http://localhost:5173"],
                "http://localhost:5173", null, "profiles", "groups", "members", "draws", "audit", "analytics"));

        public Fixture(
            bool organizer = true,
            string? actor = "actor",
            string ownerUserId = "user",
            PlanCode plan = PlanCode.Free,
            string? entitlementId = null,
            bool requiresAddress = false)
        {
            Groups = new FakeGroups(new GroupRecord(
                "group", ownerUserId, "Exchange", "", null, null, null, "USD", plan, entitlementId,
                GroupStatus.Open, "hash", [], "now", "now", RequiresAddress: requiresAddress));
            Members = new RecordingMembers(actor is null ? [] : [Member(actor) with { IsOrganizer = organizer }]);
        }

        public static MembershipRecord Member(
            string memberId,
            string wishlist = "Anything cosy",
            Address? address = null) => new(
            memberId, "group", memberId == "actor" ? "user" : $"user-{memberId}", memberId,
            IsOrganizer: false, IsParticipating: true, wishlist, "", address ?? new Address(
                "1 Main Street", "", "Springfield", "IL", "11111", "US"), "now", "now");
    }

    private sealed class FakeUser : ICurrentUser { public string UserId { get; set; } = "user"; }

    private sealed class FakeProfiles : IProfileRepository
    {
        public Task<ProfileRecord?> GetAsync(string userId, CancellationToken cancellationToken = default) =>
            Task.FromResult<ProfileRecord?>(new(userId, "User", "now", "now"));
        public Task<ProfileRecord> UpsertAsync(string userId, string displayName, bool? nonEssentialEmailsEnabled = null, Consent? consent = null, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<ProfileRecord> SetAvatarKeyAsync(string userId, string? avatarKey, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string userId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class NoopAudit : IAuditTrail
    {
        public Task RecordAsync(AuditAction action, string groupId, AuditTarget target,
            IReadOnlyDictionary<string, string>? metadata = null, string? organizationId = null,
            CancellationToken cancellationToken = default) => Task.CompletedTask;
    }

    private sealed class NoopAnalytics : IProductAnalytics
    {
        public Task TrackAsync(AnalyticsEventType type, PlanCode plan, string groupId, string idempotencyKey,
            IReadOnlyDictionary<string, string>? dimensions = null, CancellationToken cancellationToken = default) =>
            Task.CompletedTask;
    }

    private sealed class CountingWishes : IWishRepository
    {
        public List<string> QueriedMembers { get; } = [];
        public Task<IReadOnlyList<WishRecord>> GetByMemberAsync(string memberId, CancellationToken cancellationToken = default)
        {
            QueriedMembers.Add(memberId);
            return Task.FromResult<IReadOnlyList<WishRecord>>([]);
        }
        public Task<WishRecord?> GetAsync(string memberId, string wishId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task CreateAsync(WishRecord record, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<WishRecord> UpdateAsync(string memberId, string wishId, IReadOnlyDictionary<string, AttributeValue> fields, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string memberId, string wishId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteByMemberAsync(string memberId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task SetPositionsAsync(string memberId, IReadOnlyList<string> orderedWishIds, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class FakeGroups(GroupRecord seed) : IGroupRepository
    {
        private GroupRecord group = seed;
        private DrawRecord? draw;
        private int draws;

        public Task<GroupRecord?> GetAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<GroupRecord?>(group);
        public Task<GroupRecord> UpdateAsync(string groupId, IReadOnlyDictionary<string, AttributeValue> fields, GroupStatus? expectedStatus = null, CancellationToken cancellationToken = default) =>
            Task.FromResult(group);
        public Task CreateDrawAsync(string groupId, IReadOnlyDictionary<string, string> assignments, string actorUserId, CancellationToken cancellationToken = default)
        {
            group = group with { Status = GroupStatus.Drawn };
            // A distinct id per draw, exactly as the real repository mints one — the readiness
            // marker is keyed on it, so a fake reusing one id would hide the reset behaviour.
            draw = new(groupId, $"draw-{++draws}", assignments, "now", actorUserId);
            return Task.CompletedTask;
        }
        public Task ResetDrawAsync(string groupId, CancellationToken cancellationToken = default)
        {
            group = group with { Status = GroupStatus.Open };
            draw = null;
            return Task.CompletedTask;
        }
        public Task<DrawRecord?> GetDrawAsync(string groupId, CancellationToken cancellationToken = default) => Task.FromResult(draw);
        public Task<GroupRecord> CreateAsync(GroupRecord value, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class RecordingMembers(IEnumerable<MembershipRecord> items) : IMembershipRepository
    {
        public List<MembershipRecord> Items { get; } = items.ToList();
        public int MarkAssignmentViewedCalls { get; private set; }

        public Task<MembershipRecord?> GetAsync(string memberId, CancellationToken cancellationToken = default) =>
            Task.FromResult(Items.FirstOrDefault(item => item.MemberId == memberId));
        public Task<IReadOnlyList<MembershipRecord>> GetByUserAsync(string userId, CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<MembershipRecord>>(Items.Where(item => item.UserId == userId).ToList());
        public Task<IReadOnlyList<MembershipRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<MembershipRecord>>(Items.Where(item => item.GroupId == groupId).ToList());
        public Task<MembershipRecord?> GetByUserAndGroupAsync(string userId, string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult(Items.FirstOrDefault(item => item.UserId == userId && item.GroupId == groupId));
        public Task SetWishClaimAsync(string memberId, string drawId, string wishId, WishClaimRecord claim, CancellationToken cancellationToken = default)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            if (index < 0) return Task.CompletedTask;
            var current = Items[index];
            // Mirrors the repository: a map from an earlier draw is replaced, not merged into.
            var claims = current.WishClaimsDrawId == drawId && current.WishClaims is { } existing
                ? new Dictionary<string, WishClaimRecord>(existing, StringComparer.Ordinal)
                : new Dictionary<string, WishClaimRecord>(StringComparer.Ordinal);
            claims[wishId] = claim;
            Items[index] = current with { WishClaims = claims, WishClaimsDrawId = drawId };
            return Task.CompletedTask;
        }
        public Task RemoveWishClaimAsync(string memberId, string drawId, string wishId, CancellationToken cancellationToken = default)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            if (index < 0) return Task.CompletedTask;
            var current = Items[index];
            if (current.WishClaimsDrawId != drawId || current.WishClaims is not { } existing) return Task.CompletedTask;
            var claims = new Dictionary<string, WishClaimRecord>(existing, StringComparer.Ordinal);
            claims.Remove(wishId);
            Items[index] = current with { WishClaims = claims };
            return Task.CompletedTask;
        }
        public Task ClearWishClaimsAsync(string memberId, CancellationToken cancellationToken = default)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            if (index >= 0) Items[index] = Items[index] with { WishClaims = null, WishClaimsDrawId = null };
            return Task.CompletedTask;
        }
        public Task MarkAssignmentViewedAsync(string memberId, string drawId, CancellationToken cancellationToken = default)
        {
            MarkAssignmentViewedCalls++;
            var index = Items.FindIndex(item => item.MemberId == memberId);
            if (index >= 0) Items[index] = Items[index] with { AssignmentViewedDrawId = drawId };
            return Task.CompletedTask;
        }
        public Task<MembershipRecord> CreateAsync(string groupId, string userId, string displayName, bool organizer, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdatePrivateAsync(string memberId, string wishlist, string avoidances, Address address, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdateParticipationAsync(string memberId, bool participating, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task AnonymizeAsync(string memberId, string pseudonym, string displayName, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string memberId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }
}
