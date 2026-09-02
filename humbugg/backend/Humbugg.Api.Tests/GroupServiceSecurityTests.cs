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
        public FakeWishes Wishes { get; }
        public FakeQuestions Questions { get; }
        public GroupService Subject { get; }

        public Fixture(
            MembershipRecord? member,
            IReadOnlyList<string[]>? exclusions = null,
            string ownerUserId = "owner",
            PlanCode plan = PlanCode.Free,
            string? entitlementId = null,
            WishRecord[]? wishes = null,
            string callerUserId = "user")
        {
            Groups = new FakeGroups(Group(exclusions ?? [["actor", "other"]], ownerUserId, plan, entitlementId));
            Members = new FakeMembers(member is null ? [] : [member]);
            Audit = new FakeAuditTrail();
            Wishes = new FakeWishes(wishes ?? []);
            Questions = new FakeQuestions();
            Subject = new GroupService(new FakeUser(callerUserId), new FakeProfiles(), Groups, Members, Wishes, Questions, new FakeInvitations(), new MatchingService(), new PlanCatalog(new()), Audit, new FakeProductAnalytics(), new HumbuggSettings(
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

    // ── Purchase claims (#130) ───────────────────────────────────────────────────────────────────
    //
    // The feature is one sentence — a giver can mark an item planned or purchased — and one
    // invariant: the person whose list it is must never learn that anything on it is spoken for.
    // These tests attack the invariant from both directions, because the whole point of storing a
    // claim on the CLAIMANT's row rather than on the wish is that there is no projection to get
    // wrong. If that ever changes, these fail.

    /// <summary>Draws the fixture's two-member group and returns the wish seeded on the recipient.</summary>
    private static async Task<Fixture> DrawnWithWishAsync(int quantity = 1)
    {
        var wish = new WishRecord(
            "other", "wish-1", "group", "user-other", WishKind.Product, "A book",
            "", "", null, "USD", quantity, WishPriority.Normal, "", 0, "now", "now");
        var fixture = new Fixture(
            member: Fixture.Member("actor", organizer: true),
            exclusions: [],
            // The caller owns the exchange, so the reveal path is reachable from the same fixture.
            ownerUserId: "user",
            wishes: [wish]);
        fixture.Members.Items.Add(Fixture.Member("other", organizer: false));
        await fixture.Subject.DrawAsync("group", TestContext.Current.CancellationToken);
        return fixture;
    }

    [Fact]
    public async Task GiverSeesTheirOwnClaimOnTheListTheDrawGaveThem()
    {
        var fixture = await DrawnWithWishAsync();

        var assignment = await fixture.Subject.SetWishClaimAsync(
            "group", "wish-1", new SetWishClaimRequest("purchased", null), TestContext.Current.CancellationToken);

        var claimed = Assert.Single(assignment.Wishes);
        Assert.NotNull(claimed.Claim);
        Assert.Equal(WishClaimState.Purchased, claimed.Claim.State);
        // Defaulted to the whole wish rather than demanding a number for a quantity-1 item.
        Assert.Equal(1, claimed.Claim.Quantity);
    }

    /// <summary>
    /// The surprise-preservation test, asserted where it actually holds: on the STORAGE.
    /// </summary>
    /// <remarks>
    /// A claim never touches the wish row and never touches the owner's membership row, so there is
    /// no read path from which the owner could see one — including any read path added later by
    /// somebody who has not read this file. Asserting "the owner's response omitted it" would only
    /// pin today's projections; this pins the reason they cannot leak.
    /// </remarks>
    [Fact]
    public async Task AClaimTouchesNeitherTheWishNorTheWishlistOwner()
    {
        var fixture = await DrawnWithWishAsync();
        var wishBefore = Assert.Single(fixture.Wishes.All);

        await fixture.Subject.SetWishClaimAsync(
            "group", "wish-1", new SetWishClaimRequest("planned", null), TestContext.Current.CancellationToken);

        Assert.Equal(wishBefore, Assert.Single(fixture.Wishes.All));
        var owner = fixture.Members.Items.Single(member => member.MemberId == "other");
        Assert.Null(owner.WishClaims);
        Assert.Null(owner.WishClaimsDrawId);
        // And it did land — on the claimant.
        var giver = fixture.Members.Items.Single(member => member.MemberId == "actor");
        Assert.NotNull(giver.WishClaims);
        Assert.True(giver.WishClaims.ContainsKey("wish-1"));
    }

    /// <summary>
    /// A claim is never audited, and that is a privacy decision rather than an oversight: an audit
    /// row carries actor and target, so recording one would write the draw assignment into the one
    /// table an organizer is allowed to read.
    /// </summary>
    [Fact]
    public async Task ClaimingIsNeverAudited()
    {
        var fixture = await DrawnWithWishAsync();
        var before = fixture.Audit.Actions.Count;

        await fixture.Subject.SetWishClaimAsync(
            "group", "wish-1", new SetWishClaimRequest("purchased", null), TestContext.Current.CancellationToken);
        await fixture.Subject.ReleaseWishClaimAsync("group", "wish-1", TestContext.Current.CancellationToken);

        Assert.Equal(before, fixture.Audit.Actions.Count);
    }

    [Fact]
    public async Task ClaimsCanBeReleased_AndReleasingTwiceIsNotAnError()
    {
        var fixture = await DrawnWithWishAsync();
        await fixture.Subject.SetWishClaimAsync(
            "group", "wish-1", new SetWishClaimRequest("purchased", null), TestContext.Current.CancellationToken);

        var released = await fixture.Subject.ReleaseWishClaimAsync("group", "wish-1", TestContext.Current.CancellationToken);
        Assert.Null(Assert.Single(released.Wishes).Claim);

        // Idempotent: a client retrying a lost response must not be told it failed.
        var again = await fixture.Subject.ReleaseWishClaimAsync("group", "wish-1", TestContext.Current.CancellationToken);
        Assert.Null(Assert.Single(again.Wishes).Claim);
    }

    [Fact]
    public async Task PartialClaimsAreAllowedUpToWhatWasAskedFor()
    {
        var fixture = await DrawnWithWishAsync(quantity: 3);

        var partial = await fixture.Subject.SetWishClaimAsync(
            "group", "wish-1", new SetWishClaimRequest("purchased", 2), TestContext.Current.CancellationToken);
        Assert.Equal(2, Assert.Single(partial.Wishes).Claim!.Quantity);

        // Refused rather than clamped: a giver who typed 5 against a quantity of 3 has misread the
        // list, and silently recording 3 would tell them they had done what they meant to.
        foreach (var bad in new int?[] { 0, -1, 4 })
        {
            var error = await Assert.ThrowsAsync<ApiException>(() => fixture.Subject.SetWishClaimAsync(
                "group", "wish-1", new SetWishClaimRequest("purchased", bad), TestContext.Current.CancellationToken));
            Assert.Equal(400, error.StatusCode);
        }
    }

    [Fact]
    public async Task ClaimingIsRefusedBeforeADrawAndForAWishThatIsNotOnTheAssignedList()
    {
        var undrawn = new Fixture(member: Fixture.Member("actor", organizer: true), exclusions: []);
        var tooEarly = await Assert.ThrowsAsync<ApiException>(() => undrawn.Subject.SetWishClaimAsync(
            "group", "wish-1", new SetWishClaimRequest("planned", null), TestContext.Current.CancellationToken));
        Assert.Equal(409, tooEarly.StatusCode);

        var fixture = await DrawnWithWishAsync();
        var unknown = await Assert.ThrowsAsync<ApiException>(() => fixture.Subject.SetWishClaimAsync(
            "group", "not-a-wish", new SetWishClaimRequest("planned", null), TestContext.Current.CancellationToken));
        Assert.Equal(404, unknown.StatusCode);
    }

    /// <summary>
    /// A wish on somebody else's list cannot be claimed by naming its real id.
    /// </summary>
    /// <remarks>
    /// The lookup is keyed by the RECIPIENT the draw assigned, never by anything the request
    /// carries, so a wish that exists — here, one on the caller's own list — is still not found.
    /// </remarks>
    [Fact]
    public async Task AWishOnAListTheDrawDidNotAssignCannotBeClaimedByItsRealId()
    {
        var fixture = await DrawnWithWishAsync();
        fixture.Wishes.All.ToList();
        await fixture.Subject.SetWishClaimAsync(
            "group", "wish-1", new SetWishClaimRequest("planned", null), TestContext.Current.CancellationToken);

        // "actor" is assigned "other", so "other"'s own wish id is reachable; a wish belonging to
        // "actor" is not, however real its id.
        var mine = new WishRecord(
            "actor", "wish-mine", "group", "user", WishKind.Product, "My own book",
            "", "", null, "USD", 1, WishPriority.Normal, "", 0, "now", "now");
        await fixture.Wishes.CreateAsync(mine, TestContext.Current.CancellationToken);

        var error = await Assert.ThrowsAsync<ApiException>(() => fixture.Subject.SetWishClaimAsync(
            "group", "wish-mine", new SetWishClaimRequest("planned", null), TestContext.Current.CancellationToken));
        Assert.Equal(404, error.StatusCode);
    }

    /// <summary>
    /// A reset invalidates every claim, because after it you may be buying for somebody else.
    /// </summary>
    [Fact]
    public async Task ClaimsDoNotSurviveTheDrawTheyWereMadeUnder()
    {
        var fixture = await DrawnWithWishAsync();
        await fixture.Subject.SetWishClaimAsync(
            "group", "wish-1", new SetWishClaimRequest("purchased", null), TestContext.Current.CancellationToken);

        await fixture.Subject.ResetAsync("group", TestContext.Current.CancellationToken);
        await fixture.Subject.DrawAsync("group", TestContext.Current.CancellationToken);

        var assignment = await fixture.Subject.GetAssignmentAsync("group", TestContext.Current.CancellationToken);
        Assert.Null(Assert.Single(assignment.Wishes).Claim);
    }

    /// <summary>
    /// The emergency reveal shows the organizer who drew whom. It must not also show what everyone
    /// has bought: a claim is the giver's private note, and a reveal exists to unstick a draw.
    /// </summary>
    [Fact]
    public async Task TheEmergencyRevealCarriesNoClaims()
    {
        var fixture = await DrawnWithWishAsync();
        await fixture.Subject.SetWishClaimAsync(
            "group", "wish-1", new SetWishClaimRequest("purchased", null), TestContext.Current.CancellationToken);

        var revealed = await fixture.Subject.RevealAsync(
            "group", new RevealRequest("A participant lost their link."), TestContext.Current.CancellationToken);

        Assert.All(revealed.Assignments, pair => Assert.All(pair.Recipient.Wishes, wish => Assert.Null(wish.Claim)));
    }

    [Fact]
    public async Task ClearingMyOwnExchangeDataAlsoClearsMyClaims()
    {
        var fixture = await DrawnWithWishAsync();
        await fixture.Subject.SetWishClaimAsync(
            "group", "wish-1", new SetWishClaimRequest("purchased", null), TestContext.Current.CancellationToken);

        await fixture.Subject.ClearMyPrivateDataAsync("group", TestContext.Current.CancellationToken);

        var giver = fixture.Members.Items.Single(member => member.MemberId == "actor");
        Assert.Null(giver.WishClaims);
        Assert.Null(giver.WishClaimsDrawId);
    }

    private sealed class FakeUser(string userId = "user") : ICurrentUser { public string UserId => userId; }
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
            draw = new(groupId, $"draw-{CreateDrawCount}", assignments, "now", actorUserId);
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
            var index = Items.FindIndex(item => item.MemberId == memberId);
            if (index >= 0) Items[index] = Items[index] with { AssignmentViewedDrawId = drawId };
            return Task.CompletedTask;
        }
        public Task<MembershipRecord?> GetByUserAndGroupAsync(string userId, string groupId, CancellationToken cancellationToken = default) => Task.FromResult(Items.FirstOrDefault(item => item.UserId == userId && item.GroupId == groupId));
        public Task<IReadOnlyList<MembershipRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default) => Task.FromResult<IReadOnlyList<MembershipRecord>>(Items.Where(item => item.GroupId == groupId).ToList());
        public Task<IReadOnlyList<MembershipRecord>> GetByUserAsync(string userId, CancellationToken cancellationToken = default) => Task.FromResult<IReadOnlyList<MembershipRecord>>(Items.Where(item => item.UserId == userId).ToList());
        public Task<MembershipRecord?> GetAsync(string memberId, CancellationToken cancellationToken = default) => Task.FromResult(Items.FirstOrDefault(item => item.MemberId == memberId));
        public Task<MembershipRecord> CreateAsync(string groupId, string userId, string displayName, bool organizer, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdatePrivateAsync(string memberId, string wishlist, string avoidances, Address address, CancellationToken cancellationToken = default)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            var updated = Items[index] with { Wishlist = wishlist, Avoidances = avoidances, Address = address };
            Items[index] = updated;
            return Task.FromResult(updated);
        }
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
