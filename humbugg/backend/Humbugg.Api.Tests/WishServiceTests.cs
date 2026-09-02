using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class WishServiceTests
{
    // ─── Ownership ──────────────────────────────────────────────────────────────────────────────

    [Fact]
    public async Task AListReturnsOnlyTheCallersOwnWishes()
    {
        var world = new World(
            FakeWishes.Record("member-actor", "mine", "My wish"),
            FakeWishes.Record("member-other", "theirs", "Their wish"));

        var wishes = await world.Subject.ListAsync("group", TestContext.Current.CancellationToken);

        Assert.Equal(["My wish"], wishes.Select(wish => wish.Title));
    }

    // The wish id is a real id belonging to a real wish — just not the caller's. It fails because the
    // repository key is (member_id, wish_id) and the service only ever supplies the caller's member
    // id, so another member's wish is not addressable rather than merely refused.
    [Fact]
    public async Task AnotherMembersWishCannotBeUpdatedEvenByExactId()
    {
        var world = new World(FakeWishes.Record("member-other", "theirs", "Their wish"));

        var error = await Assert.ThrowsAsync<ApiException>(() =>
            world.Subject.UpdateAsync("group", "theirs", new UpdateWishRequest(
                null, "Hijacked", null, null, null, null, null, null, null), TestContext.Current.CancellationToken));

        Assert.Equal(404, error.StatusCode);
        Assert.Equal("Their wish", world.Wishes.All.Single().Title);
    }

    [Fact]
    public async Task AnotherMembersWishCannotBeDeleted()
    {
        var world = new World(FakeWishes.Record("member-other", "theirs"));

        var error = await Assert.ThrowsAsync<ApiException>(() => world.Subject.DeleteAsync("group", "theirs", TestContext.Current.CancellationToken));

        Assert.Equal(404, error.StatusCode);
        Assert.Single(world.Wishes.All);
    }

    [Fact]
    public async Task ANonMemberReachesNothing()
    {
        var world = new World(memberOfGroup: false);

        await Assert.ThrowsAsync<ApiException>(() => world.Subject.ListAsync("group", TestContext.Current.CancellationToken));
    }

    // ─── Create and validation ──────────────────────────────────────────────────────────────────

    [Fact]
    public async Task ACreatedWishTakesTheGroupsCurrencyAndSensibleDefaults()
    {
        var world = new World();

        var wish = await world.Subject.CreateAsync("group", Create(title: "A kettle"), TestContext.Current.CancellationToken);

        Assert.Equal("A kettle", wish.Title);
        Assert.Equal(WishKind.Product, wish.Kind);
        Assert.Equal(WishPriority.Normal, wish.Priority);
        Assert.Equal(1, wish.Quantity);
        Assert.Equal(0, wish.Position);
        // No price was given, so no currency is claimed either.
        Assert.Null(wish.PriceCents);
        Assert.Null(wish.Currency);
    }

    [Fact]
    public async Task APricedWishInheritsTheGroupCurrencyRatherThanAssumingDollars()
    {
        var world = new World(groupCurrency: "GBP");

        var wish = await world.Subject.CreateAsync("group", Create(priceCents: 2599), TestContext.Current.CancellationToken);

        Assert.Equal(2599, wish.PriceCents);
        Assert.Equal("GBP", wish.Currency);
    }

    [Fact]
    public async Task NewWishesAreAppendedRatherThanInsertedAtTheTop()
    {
        var world = new World();

        await world.Subject.CreateAsync("group", Create(title: "First"), TestContext.Current.CancellationToken);
        await world.Subject.CreateAsync("group", Create(title: "Second"), TestContext.Current.CancellationToken);
        await world.Subject.CreateAsync("group", Create(title: "Third"), TestContext.Current.CancellationToken);

        Assert.Equal(["First", "Second", "Third"], (await world.Subject.ListAsync("group", TestContext.Current.CancellationToken)).Select(wish => wish.Title));
    }

    [Theory]
    [InlineData("javascript:alert(1)")]
    [InlineData("data:text/html;base64,PHNjcmlwdD4=")]
    [InlineData("/relative/path")]
    [InlineData("file:///etc/passwd")]
    public async Task AUrlThatIsNotAbsoluteHttpIsRefused(string url)
    {
        var world = new World();

        var error = await Assert.ThrowsAsync<ApiException>(() =>
            world.Subject.CreateAsync("group", Create(url: url), TestContext.Current.CancellationToken));

        Assert.Equal(400, error.StatusCode);
    }

    [Fact]
    public async Task AnEmptyTitleIsRefused()
    {
        var world = new World();

        await Assert.ThrowsAsync<ApiException>(() => world.Subject.CreateAsync("group", Create(title: "   "), TestContext.Current.CancellationToken));
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    [InlineData(100)]
    public async Task AQuantityOutsideOneToNinetyNineIsRefused(int quantity)
    {
        var world = new World();

        await Assert.ThrowsAsync<ApiException>(() =>
            world.Subject.CreateAsync("group", Create(quantity: quantity), TestContext.Current.CancellationToken));
    }

    [Fact]
    public async Task ANegativePriceIsRefused()
    {
        var world = new World();

        await Assert.ThrowsAsync<ApiException>(() => world.Subject.CreateAsync("group", Create(priceCents: -1), TestContext.Current.CancellationToken));
    }

    [Fact]
    public async Task AnUnknownKindNamesTheAllowedValues()
    {
        var world = new World();

        var error = await Assert.ThrowsAsync<ApiException>(() =>
            world.Subject.CreateAsync("group", Create(kind: "wishlist"), TestContext.Current.CancellationToken));

        Assert.Contains("charity", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task TheListIsCappedSoOneMemberCannotGrowItWithoutBound()
    {
        var world = new World(Enumerable
            .Range(0, WishValidation.MaxWishesPerMember)
            .Select(index => FakeWishes.Record("member-actor", $"wish-{index}", position: index))
            .ToArray());

        var error = await Assert.ThrowsAsync<ApiException>(() => world.Subject.CreateAsync("group", Create(), TestContext.Current.CancellationToken));

        Assert.Equal(409, error.StatusCode);
    }

    // ─── Update ─────────────────────────────────────────────────────────────────────────────────

    // The bug this guards: a client sending only the field it changed should not blank everything
    // else. Absent means "leave alone", and only an explicit empty string clears a field.
    [Fact]
    public async Task AnAbsentFieldIsLeftAloneRatherThanBlanked()
    {
        var world = new World(FakeWishes.Record("member-actor", "wish") with
        {
            Details = "Blue, size M",
            Url = "https://example.com/kettle",
            PriceCents = 2599
        });

        var updated = await world.Subject.UpdateAsync("group", "wish", new UpdateWishRequest(
            null, "A better kettle", null, null, null, null, null, null, null), TestContext.Current.CancellationToken);

        Assert.Equal("A better kettle", updated.Title);
        Assert.Equal("Blue, size M", updated.Details);
        Assert.Equal("https://example.com/kettle", updated.Url);
        Assert.Equal(2599, updated.PriceCents);
    }

    [Fact]
    public async Task AnExplicitEmptyStringClearsAnOptionalField()
    {
        var world = new World(FakeWishes.Record("member-actor", "wish") with { Details = "Blue, size M" });

        var updated = await world.Subject.UpdateAsync("group", "wish", new UpdateWishRequest(
            null, null, null, null, null, null, null, null, ""), TestContext.Current.CancellationToken);

        Assert.Null(updated.Details);
    }

    [Fact]
    public async Task AnUpdateNamingNoFieldsIsRefused()
    {
        var world = new World(FakeWishes.Record("member-actor", "wish"));

        await Assert.ThrowsAsync<ApiException>(() => world.Subject.UpdateAsync(
            "group", "wish", new UpdateWishRequest(null, null, null, null, null, null, null, null, null), TestContext.Current.CancellationToken));
    }

    // ─── Reorder ────────────────────────────────────────────────────────────────────────────────

    [Fact]
    public async Task ReorderingRewritesPositionsAsADenseSequence()
    {
        var world = new World(
            FakeWishes.Record("member-actor", "a", "A", position: 0),
            FakeWishes.Record("member-actor", "b", "B", position: 1),
            FakeWishes.Record("member-actor", "c", "C", position: 2));

        var reordered = await world.Subject.ReorderAsync("group", new ReorderWishesRequest(["c", "a", "b"]), TestContext.Current.CancellationToken);

        Assert.Equal(["C", "A", "B"], reordered.Select(wish => wish.Title));
        Assert.Equal([0, 1, 2], reordered.Select(wish => wish.Position));
    }

    // A partial order would leave the unnamed wishes at stale positions, which is how duplicate
    // positions and a list that reorders itself on next load get introduced.
    [Fact]
    public async Task APartialOrderIsRefusedRatherThanHalfApplied()
    {
        var world = new World(
            FakeWishes.Record("member-actor", "a", "A", position: 0),
            FakeWishes.Record("member-actor", "b", "B", position: 1));

        await Assert.ThrowsAsync<ApiException>(() =>
            world.Subject.ReorderAsync("group", new ReorderWishesRequest(["a"]), TestContext.Current.CancellationToken));

        Assert.Equal([0, 1], world.Wishes.All.Select(wish => wish.Position));
    }

    [Fact]
    public async Task AnOrderNamingAWishTwiceIsRefused()
    {
        var world = new World(
            FakeWishes.Record("member-actor", "a", "A", position: 0),
            FakeWishes.Record("member-actor", "b", "B", position: 1));

        await Assert.ThrowsAsync<ApiException>(() =>
            world.Subject.ReorderAsync("group", new ReorderWishesRequest(["a", "a"]), TestContext.Current.CancellationToken));
    }

    [Fact]
    public async Task AnOrderNamingAnotherMembersWishIsRefused()
    {
        var world = new World(
            FakeWishes.Record("member-actor", "a", "A", position: 0),
            FakeWishes.Record("member-other", "theirs", "Theirs", position: 0));

        await Assert.ThrowsAsync<ApiException>(() =>
            world.Subject.ReorderAsync("group", new ReorderWishesRequest(["theirs"]), TestContext.Current.CancellationToken));
    }

    // ─── Fixture ────────────────────────────────────────────────────────────────────────────────

    private static CreateWishRequest Create(
        string? title = "A thing",
        string? url = null,
        string? kind = null,
        long? priceCents = null,
        int? quantity = null) =>
        new(kind, title, url, null, priceCents, null, quantity, null, null);

    private sealed class World
    {
        public FakeWishes Wishes { get; }
        public WishService Subject { get; }

        public World(params WishRecord[] seed) : this(true, "USD", seed) { }
        public World(bool memberOfGroup = true, string groupCurrency = "USD", params WishRecord[] seed)
        {
            Wishes = new FakeWishes(seed);
            var member = new MembershipRecord(
                "member-actor", "group", "user-actor", "Actor", false, true,
                "General preferences", "Avoid nothing", new Address(), "now", "now");
            Subject = new WishService(
                new FakeUser(),
                new FakeGroups(groupCurrency),
                new FakeMembers(memberOfGroup ? [member] : []),
                Wishes,
                new FakeAudit());
        }
    }

    private sealed class FakeUser : ICurrentUser { public string UserId => "user-actor"; }

    private sealed class FakeGroups(string currency) : IGroupRepository
    {
        public Task<GroupRecord?> GetAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<GroupRecord?>(new GroupRecord(
                "group", "owner", "Exchange", "", null, null, null, currency,
                PlanCode.Free, null, GroupStatus.Open, "hash", [], "now", "now"));
        public Task<GroupRecord> CreateAsync(GroupRecord record, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<GroupRecord> UpdateAsync(string groupId, IReadOnlyDictionary<string, Amazon.DynamoDBv2.Model.AttributeValue> fields, GroupStatus? expected, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task CreateDrawAsync(string groupId, IReadOnlyDictionary<string, string> assignments, string createdBy, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<DrawRecord?> GetDrawAsync(string groupId, CancellationToken cancellationToken = default) => Task.FromResult<DrawRecord?>(null);
        public Task ResetDrawAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class FakeMembers(IEnumerable<MembershipRecord> items) : IMembershipRepository
    {
        private readonly List<MembershipRecord> members = items.ToList();
        // Real behaviour, not a counter: the readiness dashboard reads this field back, so a fake
        // that swallowed the write would let a test pass on a value production never stores.
        public Task SetGiftStageAsync(string memberId, string drawId, GiftStage stage, CancellationToken cancellationToken = default)
        {
            var index = members.FindIndex(item => item.MemberId == memberId);
            // Mirrors the repository, receipt clear included: moving the stage is only allowed while
            // nobody has confirmed receipt, so the write always leaves that unset.
            if (index >= 0)
                members[index] = members[index] with
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
            var index = members.FindIndex(item => item.MemberId == memberId);
            if (index >= 0)
                members[index] = members[index] with
                {
                    GiftReceivedAt = received ? "now" : null,
                    GiftProgressDrawId = drawId,
                };
            return Task.CompletedTask;
        }
        public Task ClearGiftProgressAsync(string memberId, CancellationToken cancellationToken = default)
        {
            var index = members.FindIndex(item => item.MemberId == memberId);
            if (index >= 0)
                members[index] = members[index] with
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
            var index = members.FindIndex(item => item.MemberId == memberId);
            if (index < 0) return Task.CompletedTask;
            var current = members[index];
            // Mirrors the repository: a map from an earlier draw is replaced, not merged into.
            var claims = current.WishClaimsDrawId == drawId && current.WishClaims is { } existing
                ? new Dictionary<string, WishClaimRecord>(existing, StringComparer.Ordinal)
                : new Dictionary<string, WishClaimRecord>(StringComparer.Ordinal);
            claims[wishId] = claim;
            members[index] = current with { WishClaims = claims, WishClaimsDrawId = drawId };
            return Task.CompletedTask;
        }
        public Task RemoveWishClaimAsync(string memberId, string drawId, string wishId, CancellationToken cancellationToken = default)
        {
            var index = members.FindIndex(item => item.MemberId == memberId);
            if (index < 0) return Task.CompletedTask;
            var current = members[index];
            if (current.WishClaimsDrawId != drawId || current.WishClaims is not { } existing) return Task.CompletedTask;
            var claims = new Dictionary<string, WishClaimRecord>(existing, StringComparer.Ordinal);
            claims.Remove(wishId);
            members[index] = current with { WishClaims = claims };
            return Task.CompletedTask;
        }
        public Task ClearWishClaimsAsync(string memberId, CancellationToken cancellationToken = default)
        {
            var index = members.FindIndex(item => item.MemberId == memberId);
            if (index >= 0) members[index] = members[index] with { WishClaims = null, WishClaimsDrawId = null };
            return Task.CompletedTask;
        }
        public Task MarkAssignmentViewedAsync(string memberId, string drawId, CancellationToken cancellationToken = default)
        {
            var index = members.FindIndex(item => item.MemberId == memberId);
            if (index >= 0) members[index] = members[index] with { AssignmentViewedDrawId = drawId };
            return Task.CompletedTask;
        }
        public Task<MembershipRecord?> GetByUserAndGroupAsync(string userId, string groupId, CancellationToken cancellationToken = default) => Task.FromResult(members.FirstOrDefault(item => item.UserId == userId && item.GroupId == groupId));
        public Task<IReadOnlyList<MembershipRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default) => Task.FromResult<IReadOnlyList<MembershipRecord>>(members.Where(item => item.GroupId == groupId).ToList());
        public Task<IReadOnlyList<MembershipRecord>> GetByUserAsync(string userId, CancellationToken cancellationToken = default) => Task.FromResult<IReadOnlyList<MembershipRecord>>(members.Where(item => item.UserId == userId).ToList());
        public Task<MembershipRecord?> GetAsync(string memberId, CancellationToken cancellationToken = default) => Task.FromResult(members.FirstOrDefault(item => item.MemberId == memberId));
        public Task<MembershipRecord> CreateAsync(string groupId, string userId, string displayName, bool organizer, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdatePrivateAsync(string memberId, string wishlist, string avoidances, Address address, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdateParticipationAsync(string memberId, bool participating, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string memberId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task AnonymizeAsync(string memberId, string pseudonym, string displayName, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class FakeAudit : IAuditTrail
    {
        public Task RecordAsync(AuditAction action, string groupId, AuditTarget target, IReadOnlyDictionary<string, string>? metadata = null, string? actor = null, CancellationToken cancellationToken = default) => Task.CompletedTask;
    }
}
