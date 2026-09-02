using Amazon.DynamoDBv2.Model;
using Humbugg.Api;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Humbugg.Api.Services.Email.Core;
using Microsoft.Extensions.Logging.Abstractions;
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
        public FakeAccountDirectory Directory { get; } = new();
        public NoopEmail Email { get; }
        public GroupService Subject { get; }

        public Fixture(
            MembershipRecord? member,
            IReadOnlyList<string[]>? exclusions = null,
            string ownerUserId = "owner",
            PlanCode plan = PlanCode.Free,
            string? entitlementId = null,
            WishRecord[]? wishes = null,
            string callerUserId = "user",
            bool failMail = false)
        {
            Email = new NoopEmail { Throw = failMail };
            Groups = new FakeGroups(Group(exclusions ?? [["actor", "other"]], ownerUserId, plan, entitlementId));
            Members = new FakeMembers(member is null ? [] : [member]);
            Audit = new FakeAuditTrail();
            Wishes = new FakeWishes(wishes ?? []);
            Questions = new FakeQuestions();
            Subject = new GroupService(new FakeUser(callerUserId), new FakeProfiles(), Groups, Members, Wishes, Questions, new FakeInvitations(), new MatchingService(), new PlanCatalog(new()), Audit, new FakeProductAnalytics(), Directory, Email, new TransactionalEmailTemplates(), NullLogger<GroupService>.Instance, new HumbuggSettings(
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

    // ── Gift progress (#132) ─────────────────────────────────────────────────────────────────────
    //
    // Two facts about one gift, owned by two people: the giver's stage, and the recipient's "it
    // arrived". Keeping them as separate fields rather than one four-state enum is what lets a gift
    // handed over at a party be marked received without ever having been marked sent, and what stops
    // a recipient overwriting the giver's own record of what they did.

    [Fact]
    public async Task AGiverMovesTheirOwnGiftThroughTheThreeStages()
    {
        var fixture = await DrawnWithWishAsync();

        foreach (var stage in new[] { "choosing", "purchased", "sent" })
        {
            var assignment = await fixture.Subject.SetGiftStageAsync(
                "group", new SetGiftStageRequest(stage), TestContext.Current.CancellationToken);
            Assert.Equal(stage, assignment.Gift!.Stage.ToString().ToLowerInvariant());
            Assert.NotNull(assignment.Gift.StageAt);
        }

        // A returned item really does go back to choosing — corrections are legitimate, and the only
        // ordering rule enforced is the one below.
        var back = await fixture.Subject.SetGiftStageAsync(
            "group", new SetGiftStageRequest("choosing"), TestContext.Current.CancellationToken);
        Assert.Equal(GiftStage.Choosing, back.Gift!.Stage);
    }

    [Fact]
    public async Task AnUnknownStageIsRefused()
    {
        var fixture = await DrawnWithWishAsync();
        foreach (var bad in new[] { null, "", "received", "posted" })
        {
            var error = await Assert.ThrowsAsync<ApiException>(() => fixture.Subject.SetGiftStageAsync(
                "group", new SetGiftStageRequest(bad), TestContext.Current.CancellationToken));
            Assert.Equal(400, error.StatusCode);
        }
    }

    /// <summary>
    /// The recipient's confirmation lands on the GIVER's row, and they never learn whose it was.
    /// </summary>
    [Fact]
    public async Task TheRecipientConfirmsReceiptOnToTheGiversRow()
    {
        var fixture = await DrawnWithWishAsync();
        await fixture.Subject.SetGiftStageAsync(
            "group", new SetGiftStageRequest("sent"), TestContext.Current.CancellationToken);

        // "other" gives to "actor" in a two-person draw, so the caller confirming receipt writes on
        // to "other"'s row — resolved server-side by inverting the draw.
        var receipt = await fixture.Subject.SetGiftReceivedAsync(
            "group", new SetGiftReceivedRequest(true), TestContext.Current.CancellationToken);

        Assert.True(receipt.Received);
        Assert.NotNull(receipt.ReceivedAt);
        Assert.NotNull(fixture.Members.Items.Single(member => member.MemberId == "other").GiftReceivedAt);
        // And not on their own row: the two facts belong to two different gifts.
        Assert.Null(fixture.Members.Items.Single(member => member.MemberId == "actor").GiftReceivedAt);
    }

    /// <summary>
    /// The one ordering rule that is actually true: a gift somebody has confirmed receiving was
    /// obviously bought, so the giver cannot walk the stage back afterwards.
    /// </summary>
    [Fact]
    public async Task AGiverCannotMoveAGiftTheRecipientHasAlreadyConfirmed()
    {
        var fixture = await DrawnWithWishAsync();
        await fixture.Subject.SetGiftStageAsync(
            "group", new SetGiftStageRequest("sent"), TestContext.Current.CancellationToken);
        var drawId = (await fixture.Groups.GetDrawAsync("group", TestContext.Current.CancellationToken))!.DrawId;

        // Staged on the row directly rather than through the recipient's endpoint: in a two-person
        // draw the caller's own giver is also their recipient, and routing through the API would
        // land the receipt on the OTHER row — which is correct behaviour and the wrong setup for
        // this test. What is under test is the guard on the caller's own gift.
        var index = fixture.Members.Items.FindIndex(member => member.MemberId == "actor");
        fixture.Members.Items[index] = fixture.Members.Items[index] with
        {
            GiftReceivedAt = "now",
            GiftProgressDrawId = drawId,
        };

        var error = await Assert.ThrowsAsync<ApiException>(() => fixture.Subject.SetGiftStageAsync(
            "group", new SetGiftStageRequest("choosing"), TestContext.Current.CancellationToken));
        Assert.Equal(409, error.StatusCode);
    }

    [Fact]
    public async Task ReceiptCanBeTakenBack()
    {
        var fixture = await DrawnWithWishAsync();
        await fixture.Subject.SetGiftReceivedAsync(
            "group", new SetGiftReceivedRequest(true), TestContext.Current.CancellationToken);

        var cleared = await fixture.Subject.SetGiftReceivedAsync(
            "group", new SetGiftReceivedRequest(false), TestContext.Current.CancellationToken);

        Assert.False(cleared.Received);
        Assert.Null(cleared.ReceivedAt);
    }

    /// <summary>
    /// Progress is audited — unlike a purchase claim — and safely, because every row names only the
    /// actor and a stage.
    /// </summary>
    [Fact]
    public async Task EveryTransitionIsAuditedWithoutNamingTheOtherParty()
    {
        var fixture = await DrawnWithWishAsync();
        fixture.Audit.Actions.Clear();
        fixture.Audit.Targets.Clear();

        await fixture.Subject.SetGiftStageAsync(
            "group", new SetGiftStageRequest("purchased"), TestContext.Current.CancellationToken);
        await fixture.Subject.SetGiftReceivedAsync(
            "group", new SetGiftReceivedRequest(true), TestContext.Current.CancellationToken);

        Assert.Equal(
            [AuditAction.GiftProgressChanged, AuditAction.GiftProgressChanged],
            fixture.Audit.Actions);
        // Both rows target the ACTOR. A row naming the other party would be the draw assignment, in
        // the one table an organizer is allowed to read.
        Assert.All(fixture.Audit.Targets, target => Assert.Equal("actor", target.Id));
    }

    /// <summary>A reset starts the gift again, because it may now be for somebody else.</summary>
    [Fact]
    public async Task GiftProgressDoesNotSurviveTheDrawItWasMadeUnder()
    {
        var fixture = await DrawnWithWishAsync();
        await fixture.Subject.SetGiftStageAsync(
            "group", new SetGiftStageRequest("sent"), TestContext.Current.CancellationToken);

        await fixture.Subject.ResetAsync("group", TestContext.Current.CancellationToken);
        await fixture.Subject.DrawAsync("group", TestContext.Current.CancellationToken);

        var assignment = await fixture.Subject.GetAssignmentAsync("group", TestContext.Current.CancellationToken);
        Assert.Equal(GiftStage.Choosing, assignment.Gift!.Stage);
        Assert.Null(assignment.Gift.StageAt);
        Assert.False(assignment.Gift.Received);
    }

    [Fact]
    public async Task TheEmergencyRevealCarriesNoGiftStatus()
    {
        var fixture = await DrawnWithWishAsync();
        await fixture.Subject.SetGiftStageAsync(
            "group", new SetGiftStageRequest("sent"), TestContext.Current.CancellationToken);

        var revealed = await fixture.Subject.RevealAsync(
            "group", new RevealRequest("A participant lost their link."), TestContext.Current.CancellationToken);

        Assert.All(revealed.Assignments, pair => Assert.Null(pair.Recipient.Gift));
    }

    [Fact]
    public async Task ClearingMyOwnExchangeDataAlsoClearsBothHalvesOfMyGiftProgress()
    {
        var fixture = await DrawnWithWishAsync();
        await fixture.Subject.SetGiftStageAsync(
            "group", new SetGiftStageRequest("sent"), TestContext.Current.CancellationToken);
        await fixture.Subject.SetGiftReceivedAsync(
            "group", new SetGiftReceivedRequest(true), TestContext.Current.CancellationToken);

        await fixture.Subject.ClearMyPrivateDataAsync("group", TestContext.Current.CancellationToken);

        var mine = fixture.Members.Items.Single(member => member.MemberId == "actor");
        Assert.Null(mine.GiftStage);
        Assert.Null(mine.GiftProgressDrawId);
        // And the receipt they left on their giver's row, which lives somewhere else by design.
        Assert.Null(fixture.Members.Items.Single(member => member.MemberId == "other").GiftReceivedAt);
    }

    // ── Draw notifications (#137) ────────────────────────────────────────────────────────────────
    //
    // The one message without which the exchange does not work. Until #137 it was never sent: the
    // template existed and nothing called it, and the only address Humbugg could reach was on an
    // accepted managed invitation — a Plus capability, so a Free exchange could not be told at all.

    [Fact]
    public async Task ADrawTellsEveryParticipantWithAVerifiedAddress()
    {
        var fixture = new Fixture(member: Fixture.Member("actor", organizer: true), exclusions: []);
        fixture.Members.Items.Add(Fixture.Member("other", organizer: false));
        fixture.Directory.Emails["user"] = "actor@example.test";
        fixture.Directory.Emails["user-other"] = "other@example.test";

        await fixture.Subject.DrawAsync("group", TestContext.Current.CancellationToken);

        Assert.Equal(2, fixture.Email.Sent.Count);
        Assert.Equal(
            ["actor@example.test", "other@example.test"],
            fixture.Email.Sent.Select(message => message.ToAddress).Order(StringComparer.Ordinal));
        Assert.All(fixture.Email.Sent, message =>
            Assert.Equal(Humbugg.Api.Services.Email.Core.EmailCategory.DrawCompleted, message.Category));
    }

    /// <summary>
    /// An account with no verified address is sent nothing, and everybody else still is.
    /// </summary>
    /// <remarks>
    /// Both halves matter. Skipping the unverified one is the safety rule; carrying on afterwards is
    /// what stops one unconfirmed signup silently costing forty-nine other people their notification.
    /// </remarks>
    [Fact]
    public async Task AnUnreachableParticipantDoesNotStopTheOthersBeingTold()
    {
        var fixture = new Fixture(member: Fixture.Member("actor", organizer: true), exclusions: []);
        fixture.Members.Items.Add(Fixture.Member("other", organizer: false));
        fixture.Directory.Emails["user-other"] = "other@example.test";

        await fixture.Subject.DrawAsync("group", TestContext.Current.CancellationToken);

        Assert.Equal("other@example.test", Assert.Single(fixture.Email.Sent).ToAddress);
    }

    /// <summary>
    /// The notification never carries the recipient's name.
    /// </summary>
    /// <remarks>
    /// The whole point of the link is that the name is behind a sign-in. Putting it in an inbox would
    /// hand the assignment to anybody who reads over a shoulder — and it is a claim the template
    /// itself makes, so it is worth pinning rather than trusting.
    /// </remarks>
    [Fact]
    public async Task ADrawNotificationNamesNobodysRecipient()
    {
        var fixture = new Fixture(member: Fixture.Member("actor", organizer: true), exclusions: []);
        fixture.Members.Items.Add(Fixture.Member("other", organizer: false));
        fixture.Directory.Emails["user"] = "actor@example.test";
        fixture.Directory.Emails["user-other"] = "other@example.test";

        await fixture.Subject.DrawAsync("group", TestContext.Current.CancellationToken);

        foreach (var message in fixture.Email.Sent)
        {
            var whole = $"{message.Subject} {message.HtmlBody} {message.TextBody}";
            // Each person is greeted by name; nobody is told whose name they drew. With a two-person
            // draw the only way to satisfy both is to name only the addressee.
            var other = message.ToAddress.StartsWith("actor", StringComparison.Ordinal) ? "other" : "actor";
            Assert.DoesNotContain(other, whole, StringComparison.OrdinalIgnoreCase);
        }
    }

    /// <summary>
    /// A draw is not undone by a mail failure.
    /// </summary>
    /// <remarks>
    /// The assignments are written and audited before any notification is attempted, so a failure
    /// here has to be swallowed — otherwise a Cognito hiccup would surface to the organizer as a
    /// draw that "failed" after it had already happened.
    /// </remarks>
    [Fact]
    public async Task ADrawSurvivesAFailingMailer()
    {
        var fixture = new Fixture(
            member: Fixture.Member("actor", organizer: true), exclusions: [], failMail: true);
        fixture.Members.Items.Add(Fixture.Member("other", organizer: false));
        fixture.Directory.Emails["user"] = "actor@example.test";

        var assignment = await fixture.Subject.DrawAsync("group", TestContext.Current.CancellationToken);

        Assert.Equal("other", assignment.MemberId);
        Assert.Equal(1, fixture.Groups.CreateDrawCount);
    }

    // ── Organizer editing and roster management (#135) ───────────────────────────────────────────

    /// <summary>
    /// Two organizers editing at once: the second save is refused rather than silently winning.
    /// </summary>
    /// <remarks>
    /// Last-write-wins is the default and it is the wrong default here, because the loser is never
    /// told. Somebody rewrites the description, somebody else changes the date from a page loaded ten
    /// minutes earlier, and the description quietly reverts with nobody the wiser. The precondition
    /// is the `updated_at` the row already carries, so no version attribute exists to forget to bump.
    /// </remarks>
    [Fact]
    public async Task AnEditAgainstAStaleReadIsRefusedRatherThanFlatteningTheOtherOne()
    {
        var fixture = new Fixture(member: Fixture.Member("actor", organizer: true));
        var loaded = await fixture.Subject.GetAsync("group", TestContext.Current.CancellationToken);

        await fixture.Subject.UpdateAsync(
            "group",
            new UpdateGroupRequest("Renamed", null, null, null, null, ExpectedUpdatedAt: loaded.UpdatedAt),
            TestContext.Current.CancellationToken);

        // Somebody else has written since; the same `updated_at` is now stale.
        fixture.Groups.Touch();
        var error = await Assert.ThrowsAsync<ApiException>(() => fixture.Subject.UpdateAsync(
            "group",
            new UpdateGroupRequest(null, "A new description", null, null, null, ExpectedUpdatedAt: loaded.UpdatedAt),
            TestContext.Current.CancellationToken));

        Assert.Equal(409, error.StatusCode);
        Assert.Contains("Reload", error.Message, StringComparison.Ordinal);
    }

    /// <summary>An edit that sends no expectation is not conflict-checked, and still works.</summary>
    /// <remarks>The readiness dashboard's address switch flips one field from a value it just
    /// computed; there is nothing for it to conflict with, and demanding a token would be ceremony.</remarks>
    [Fact]
    public async Task AnEditWithNoExpectationIsUnaffected()
    {
        var fixture = new Fixture(member: Fixture.Member("actor", organizer: true));
        fixture.Groups.Touch();

        var updated = await fixture.Subject.UpdateAsync(
            "group", new UpdateGroupRequest(null, null, null, null, null, RequiresAddress: true),
            TestContext.Current.CancellationToken);

        Assert.True(updated.RequiresAddress);
    }

    /// <summary>
    /// Instructions are Free, and are not the customization's instructions.
    /// </summary>
    [Fact]
    public async Task InstructionsAreEditableWithoutPlus()
    {
        var fixture = new Fixture(member: Fixture.Member("actor", organizer: true), plan: PlanCode.Free);

        var updated = await fixture.Subject.UpdateAsync(
            "group",
            new UpdateGroupRequest(null, null, null, null, null, Instructions: "  Bring it wrapped to the office.  "),
            TestContext.Current.CancellationToken);

        Assert.Equal("Bring it wrapped to the office.", updated.Instructions);
        // Untouched: the two fields are different things for different audiences.
        Assert.Null(updated.Customization);
    }

    [Fact]
    public async Task OnlyTheOwnerRemovesSomebody_AndNeverThemselves()
    {
        var coOrganizer = new Fixture(member: Fixture.Member("actor", organizer: true), ownerUserId: "somebody-else");
        coOrganizer.Members.Items.Add(Fixture.Member("other", organizer: false));
        Assert.Equal(403, (await Assert.ThrowsAsync<ApiException>(() =>
            coOrganizer.Subject.RemoveMemberAsync("group", "other", TestContext.Current.CancellationToken))).StatusCode);

        var participant = new Fixture(member: Fixture.Member("actor", organizer: false));
        participant.Members.Items.Add(Fixture.Member("other", organizer: false));
        Assert.Equal(403, (await Assert.ThrowsAsync<ApiException>(() =>
            participant.Subject.RemoveMemberAsync("group", "other", TestContext.Current.CancellationToken))).StatusCode);

        var owner = new Fixture(member: Fixture.Member("actor", organizer: true), ownerUserId: "user");
        Assert.Equal(409, (await Assert.ThrowsAsync<ApiException>(() =>
            owner.Subject.RemoveMemberAsync("group", "actor", TestContext.Current.CancellationToken))).StatusCode);
    }

    /// <summary>
    /// Removal takes everything the departing member authored — the same list leaving does.
    /// </summary>
    /// <remarks>
    /// What has to be swept has grown every release: wishes, purchase claims, question threads at
    /// both ends, gift progress on two rows. Removal and leaving share one method precisely so the
    /// list cannot be right in one and stale in the other.
    /// </remarks>
    [Fact]
    public async Task RemovingSomebodyTakesEverythingTheyAuthored()
    {
        var wish = new WishRecord(
            "other", "wish-1", "group", "user-other", WishKind.Product, "A book",
            "", "", null, "USD", 1, WishPriority.Normal, "", 0, "now", "now");
        var fixture = new Fixture(
            member: Fixture.Member("actor", organizer: true), ownerUserId: "user",
            exclusions: [["actor", "other"]], wishes: [wish]);
        fixture.Members.Items.Add(Fixture.Member("other", organizer: false));

        await fixture.Subject.RemoveMemberAsync("group", "other", TestContext.Current.CancellationToken);

        Assert.DoesNotContain(fixture.Members.Items, member => member.MemberId == "other");
        Assert.Empty(fixture.Wishes.All);
        Assert.Contains("other", fixture.Questions.DeletedForMembers);
        Assert.Contains(AuditAction.ParticipantRemoved, fixture.Audit.Actions);
    }

    /// <summary>
    /// A pair naming somebody who has gone is dropped, not left to poison the draw.
    /// </summary>
    /// <remarks>
    /// A stale exclusion is not inert: the matcher reads it as a constraint, so on a small roster it
    /// can make an otherwise solvable draw impossible — and the error blames the draw rather than the
    /// person who left three weeks earlier.
    /// </remarks>
    [Fact]
    public async Task RemovingSomebodyPrunesTheExclusionsNamingThem()
    {
        var fixture = new Fixture(
            member: Fixture.Member("actor", organizer: true), ownerUserId: "user",
            exclusions: [["actor", "other"], ["actor", "third"]]);
        fixture.Members.Items.Add(Fixture.Member("other", organizer: false));
        fixture.Members.Items.Add(Fixture.Member("third", organizer: false));

        await fixture.Subject.RemoveMemberAsync("group", "other", TestContext.Current.CancellationToken);

        var remaining = fixture.Groups.LastExclusions;
        Assert.NotNull(remaining);
        Assert.Equal([["actor", "third"]], remaining);
    }

    /// <summary>After a draw, removal is refused: reset first, or somebody buys for a ghost.</summary>
    [Fact]
    public async Task RemovingSomebodyAfterTheDrawIsRefused()
    {
        var fixture = new Fixture(
            member: Fixture.Member("actor", organizer: true), ownerUserId: "user", exclusions: []);
        fixture.Members.Items.Add(Fixture.Member("other", organizer: false));
        await fixture.Subject.DrawAsync("group", TestContext.Current.CancellationToken);

        var error = await Assert.ThrowsAsync<ApiException>(() =>
            fixture.Subject.RemoveMemberAsync("group", "other", TestContext.Current.CancellationToken));

        Assert.Equal(409, error.StatusCode);
        Assert.Contains(fixture.Members.Items, member => member.MemberId == "other");
    }

    // ── Repeating an exchange (#136) ─────────────────────────────────────────────────────────────

    /// <summary>
    /// The privacy guarantee, and it is structural: the new exchange has nowhere to put last year's
    /// private data because it has no memberships except the organizer's.
    /// </summary>
    [Fact]
    public async Task RepeatingCarriesTheOrganizersWordsAndNothingPrivate()
    {
        var wish = new WishRecord(
            "other", "wish-1", "group", "user-other", WishKind.Product, "A book",
            "", "", null, "USD", 1, WishPriority.Normal, "", 0, "now", "now");
        var fixture = new Fixture(
            member: Fixture.Member("actor", organizer: true), ownerUserId: "user", exclusions: [],
            wishes: [wish]);
        fixture.Members.Items.Add(Fixture.Member("other", organizer: false));

        var repeated = await fixture.Subject.RepeatAsync(
            "group", new RepeatExchangeRequest("Next year", "2027-12-19", null),
            TestContext.Current.CancellationToken);

        Assert.Equal("Next year", repeated.Group.Name);
        Assert.NotEqual("group", repeated.Group.GroupId);
        // Only the organizer is in it. Everything private belongs to a membership, so there is
        // nowhere for a wishlist, an address, a claim, a conversation or a gift stage to land.
        var member = Assert.Single(repeated.Group.Members);
        Assert.True(member.IsOrganizer);
        // The prior roster comes back as names to send the link to, never as members.
        Assert.Equal(["other"], repeated.PriorParticipants);
        Assert.Contains("#invite=", repeated.InviteUrl, StringComparison.Ordinal);
    }

    /// <summary>The source is read and never touched: last year stays exactly as it was.</summary>
    [Fact]
    public async Task RepeatingLeavesTheExchangeItCameFromAlone()
    {
        var fixture = new Fixture(
            member: Fixture.Member("actor", organizer: true), ownerUserId: "user",
            exclusions: [["actor", "other"]]);
        fixture.Members.Items.Add(Fixture.Member("other", organizer: false));
        var before = await fixture.Subject.GetAsync("group", TestContext.Current.CancellationToken);

        await fixture.Subject.RepeatAsync(
            "group", new RepeatExchangeRequest(null, null, null), TestContext.Current.CancellationToken);

        var after = await fixture.Subject.GetAsync("group", TestContext.Current.CancellationToken);
        Assert.Equal(before.Name, after.Name);
        Assert.Equal(before.Exclusions.Count, after.Exclusions.Count);
        Assert.Equal(before.Members.Count, after.Members.Count);
    }

    /// <summary>
    /// Exclusions are translated into the new exchange's member ids, not copied.
    /// </summary>
    /// <remarks>
    /// A member id is <c>sha256(groupId:userId)</c>, so a literal copy would name ids belonging to
    /// last year's group and quietly constrain nobody. Translating them is only possible because the
    /// id is derived rather than random.
    /// </remarks>
    [Fact]
    public async Task CopiedExclusionsAreRewrittenForTheNewExchange()
    {
        var fixture = new Fixture(
            member: Fixture.Member("actor", organizer: true), ownerUserId: "user",
            exclusions: [["actor", "other"]]);
        fixture.Members.Items.Add(Fixture.Member("other", organizer: false));

        var repeated = await fixture.Subject.RepeatAsync(
            "group", new RepeatExchangeRequest(null, null, null, CopyExclusions: true),
            TestContext.Current.CancellationToken);

        var pair = Assert.Single(repeated.Group.Exclusions);
        // Not the old ids — the new ones, which each person will have the moment they join.
        Assert.DoesNotContain("actor", pair);
        Assert.DoesNotContain("other", pair);
        // BOTH sides sorted. A member id is a hash, so which of the two sorts first depends on the
        // randomly generated group id — comparing a fixed order against a sorted one passes or fails
        // by coin flip, which is exactly how this test behaved before the Order() on the left.
        Assert.Equal(
            new[]
            {
                Humbugg.Api.Data.MembershipRepository.MemberId(repeated.Group.GroupId, "user"),
                Humbugg.Api.Data.MembershipRepository.MemberId(repeated.Group.GroupId, "user-other"),
            }.Order(StringComparer.Ordinal),
            pair.Order(StringComparer.Ordinal));
    }

    /// <summary>
    /// A pair naming somebody who is no longer resolvable is dropped rather than translated.
    /// </summary>
    /// <remarks>
    /// A deleted account leaves a membership row that has been anonymized, or none at all. Carrying
    /// their pair forward would put a constraint on next year's draw that names nobody and that no
    /// organizer could explain, let alone remove.
    /// </remarks>
    [Fact]
    public async Task AnExclusionNamingSomebodyWhoIsGoneIsNotCarriedForward()
    {
        var fixture = new Fixture(
            member: Fixture.Member("actor", organizer: true), ownerUserId: "user",
            exclusions: [["actor", "departed"], ["actor", "other"]]);
        fixture.Members.Items.Add(Fixture.Member("other", organizer: false));
        // "departed" is named by an exclusion and is not on the roster.

        var repeated = await fixture.Subject.RepeatAsync(
            "group", new RepeatExchangeRequest(null, null, null, CopyExclusions: true),
            TestContext.Current.CancellationToken);

        Assert.Single(repeated.Group.Exclusions);
    }

    [Fact]
    public async Task DetailsAndExclusionsAreOptIn()
    {
        var fixture = new Fixture(
            member: Fixture.Member("actor", organizer: true), ownerUserId: "user",
            exclusions: [["actor", "other"]]);
        fixture.Members.Items.Add(Fixture.Member("other", organizer: false));

        var bare = await fixture.Subject.RepeatAsync(
            "group", new RepeatExchangeRequest(null, null, null, CopyDetails: false),
            TestContext.Current.CancellationToken);

        Assert.Equal("", bare.Group.Description);
        Assert.Null(bare.Group.SpendingLimit);
        // Exclusions default to off: last year's "these two are a couple" may not be true any more,
        // and a constraint nobody asked for is worse than one they have to re-add.
        Assert.Empty(bare.Group.Exclusions);
    }

    /// <summary>Plus does not travel: it is bought per exchange, and repeating is not a way round that.</summary>
    [Fact]
    public async Task ARepeatedExchangeIsAlwaysFree()
    {
        var fixture = new Fixture(
            member: Fixture.Member("actor", organizer: true), ownerUserId: "user", exclusions: [],
            plan: PlanCode.Plus, entitlementId: "plus:group");

        var repeated = await fixture.Subject.RepeatAsync(
            "group", new RepeatExchangeRequest(null, null, null), TestContext.Current.CancellationToken);

        Assert.Equal(PlanCode.Free, repeated.Group.Plan);
        Assert.Null(repeated.Group.Customization);
    }

    [Fact]
    public async Task OnlyTheOwnerRepeatsAnExchange()
    {
        var coOrganizer = new Fixture(
            member: Fixture.Member("actor", organizer: true), ownerUserId: "somebody-else");

        var error = await Assert.ThrowsAsync<ApiException>(() => coOrganizer.Subject.RepeatAsync(
            "group", new RepeatExchangeRequest(null, null, null), TestContext.Current.CancellationToken));

        Assert.Equal(403, error.StatusCode);
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
        // Repeating an exchange (#136) creates a SECOND one, so the fake can no longer be a single
        // record. The original stays in `group` because everything else addresses it by name.
        private readonly Dictionary<string, GroupRecord> extra = new(StringComparer.Ordinal);
        private DrawRecord? draw;
        public int UpdateCount { get; private set; }
        public int CreateDrawCount { get; private set; }
        public int ResetDrawCount { get; private set; }
        public Task<GroupRecord?> GetAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult(groupId == group.GroupId ? group : extra.GetValueOrDefault(groupId));

        public Task<GroupRecord> CreateAsync(GroupRecord value, CancellationToken cancellationToken = default)
        {
            extra[value.GroupId] = value;
            return Task.FromResult(value);
        }
        /// <summary>The exclusions the last update wrote, for the pruning tests.</summary>
        public IReadOnlyList<string[]>? LastExclusions { get; private set; }

        /// <summary>Simulates somebody else writing: the row's `updated_at` moves on.</summary>
        public void Touch() => group = group with { UpdatedAt = $"touched-{++touches}" };
        private int touches;

        public Task<GroupRecord> UpdateAsync(string groupId, IReadOnlyDictionary<string, AttributeValue> fields, GroupStatus? expectedStatus = null, string? expectedUpdatedAt = null, CancellationToken cancellationToken = default)
        {
            UpdateCount++;
            // The real repository enforces this with a DynamoDB condition; the fake enforces the same
            // rule so a test can tell a refusal from a silent overwrite.
            if (expectedUpdatedAt is not null && expectedUpdatedAt != group.UpdatedAt)
                throw new ConditionalCheckFailedException("stale");
            if (fields.TryGetValue("exclusions", out var exclusions))
                LastExclusions = exclusions.L?
                    .Select(pair => pair.L?.Select(entry => entry.S ?? "").ToArray() ?? [])
                    .ToList();
            if (groupId != group.GroupId && extra.TryGetValue(groupId, out var other))
                return Task.FromResult(extra[groupId] = Apply(other, fields));
            group = Apply(group, fields);
            return Task.FromResult(group);
        }

        /// <summary>Applies the fields the tests actually read back, so a save is observable.</summary>
        private static GroupRecord Apply(GroupRecord current, IReadOnlyDictionary<string, AttributeValue> fields)
        {
            foreach (var (field, value) in fields)
                current = field switch
                {
                    "name" => current with { Name = value.S },
                    "description" => current with { Description = value.S },
                    "instructions" => current with { Instructions = value.S },
                    "requires_address" => current with { RequiresAddress = value.BOOL == true },
                    _ => current,
                };
            return current with { UpdatedAt = $"{current.UpdatedAt}+" };
        }
        public Task CreateDrawAsync(string groupId, IReadOnlyDictionary<string, string> assignments, string actorUserId, CancellationToken cancellationToken = default)
        {
            CreateDrawCount++;
            group = group with { Status = GroupStatus.Drawn };
            draw = new(groupId, $"draw-{CreateDrawCount}", assignments, "now", actorUserId);
            return Task.CompletedTask;
        }
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
        // Kept as well as the action, because for gift progress WHAT is targeted is the privacy
        // property under test: a row naming the other party would be the draw assignment.
        public List<AuditTarget> Targets { get; } = [];
        public Task RecordAsync(AuditAction action, string groupId, AuditTarget target,
            IReadOnlyDictionary<string, string>? metadata = null, string? organizationId = null, CancellationToken cancellationToken = default)
        {
            Actions.Add(action);
            Targets.Add(target);
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
        public Task SetGiftStageAsync(string memberId, string drawId, GiftStage stage, CancellationToken cancellationToken = default)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            // Mirrors the repository, receipt clear included: moving the stage is only allowed while
            // nobody has confirmed receipt, so the write always leaves that unset.
            if (index >= 0)
                Items[index] = Items[index] with
                {
                    GiftStage = stage,
                    GiftStageAt = "now",
                    GiftReceivedAt = null,
                    GiftProgressDrawId = drawId,
                };
            return Task.CompletedTask;
        }
        public Task SetGiftReceivedAsync(string memberId, string drawId, bool received, CancellationToken cancellationToken = default)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            if (index >= 0)
                Items[index] = Items[index] with
                {
                    GiftReceivedAt = received ? "now" : null,
                    GiftProgressDrawId = drawId,
                };
            return Task.CompletedTask;
        }
        public Task ClearGiftProgressAsync(string memberId, CancellationToken cancellationToken = default)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            if (index >= 0)
                Items[index] = Items[index] with
                {
                    GiftStage = null,
                    GiftStageAt = null,
                    GiftReceivedAt = null,
                    GiftProgressDrawId = null,
                };
            return Task.CompletedTask;
        }
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
        public Task<MembershipRecord> CreateAsync(string groupId, string userId, string displayName, bool organizer, CancellationToken cancellationToken = default)
        {
            var record = MembershipRepository.NewRecord(groupId, userId, displayName, organizer);
            Items.Add(record);
            return Task.FromResult(record);
        }
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
        public Task DeleteAsync(string memberId, CancellationToken cancellationToken = default)
        {
            Items.RemoveAll(item => item.MemberId == memberId);
            return Task.CompletedTask;
        }
        public Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task AnonymizeAsync(string memberId, string pseudonym, string displayName, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }
}
