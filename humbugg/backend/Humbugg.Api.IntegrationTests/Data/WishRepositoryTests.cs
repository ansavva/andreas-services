using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Data;
using Humbugg.Api.Models;

using Xunit;

namespace Humbugg.Api.IntegrationTests.Data;

public sealed class WishRepositoryTests(DevStackFixture stack) : DevStackTest(stack)
{
    private WishRepository Repository => new(Db, Settings);

    private WishRecord NewWish(string memberId, string wishId, int position = 0, long? priceCents = null) => new(
        memberId, wishId, GroupId: "itest-group", UserId: "itest-user",
        Kind: WishKind.Product, Title: "Wool socks", Url: "https://example.test/socks",
        ImageUrl: "", PriceCents: priceCents, Currency: "USD", Quantity: 2,
        Priority: WishPriority.High, Details: "Size L", Position: position,
        CreatedAt: Now(), UpdatedAt: Now());

    private async Task<WishRecord> CreateTracked(string memberId, int position = 0, long? priceCents = null)
    {
        var record = NewWish(memberId, Uid("wish"), position, priceCents);
        await Repository.CreateAsync(record);
        CleanupItem(Settings.WishesTable, "member_id", memberId, "wish_id", record.WishId);
        return record;
    }

    [IntegrationFact]
    public async Task Create_and_get_round_trip_including_absent_price()
    {
        var memberId = Uid("member");
        var priced = await CreateTracked(memberId, priceCents: 1999);
        var unpriced = await CreateTracked(memberId, position: 1);

        var fetchedPriced = await Repository.GetAsync(memberId, priced.WishId);
        Assert.Equal(priced, fetchedPriced);
        Assert.Equal(WishKind.Product, fetchedPriced!.Kind);
        Assert.Equal(WishPriority.High, fetchedPriced.Priority);

        // No price is stored as no attribute, and must read back as null — not zero.
        var fetchedUnpriced = await Repository.GetAsync(memberId, unpriced.WishId);
        Assert.Null(fetchedUnpriced!.PriceCents);
    }

    [IntegrationFact]
    public async Task Listing_orders_by_position_then_creation_time()
    {
        var memberId = Uid("member");
        var second = await CreateTracked(memberId, position: 1);
        var first = await CreateTracked(memberId, position: 0);

        var list = await Repository.GetByMemberAsync(memberId);
        Assert.Equal([first.WishId, second.WishId], list.Select(wish => wish.WishId).ToList());
    }

    [IntegrationFact]
    public async Task Update_rewrites_named_fields_and_requires_the_row()
    {
        var memberId = Uid("member");
        var wish = await CreateTracked(memberId);

        var updated = await Repository.UpdateAsync(memberId, wish.WishId, new Dictionary<string, AttributeValue>
        {
            ["title"] = new("Cotton socks"),
            ["priority"] = new(nameof(WishPriority.Low))
        });
        Assert.Equal("Cotton socks", updated.Title);
        Assert.Equal(WishPriority.Low, updated.Priority);

        // Addressing a wish under the wrong member is indistinguishable from a missing wish:
        // the owner is part of the key, so this is the authorization property of the table.
        await Assert.ThrowsAsync<ConditionalCheckFailedException>(() => Repository.UpdateAsync(
            Uid("member"), wish.WishId, new Dictionary<string, AttributeValue> { ["title"] = new("Stolen") }));
    }

    [IntegrationFact]
    public async Task SetPositions_rewrites_a_dense_sequence()
    {
        var memberId = Uid("member");
        var wishA = await CreateTracked(memberId, position: 0);
        var wishB = await CreateTracked(memberId, position: 1);
        var wishC = await CreateTracked(memberId, position: 2);

        await Repository.SetPositionsAsync(memberId, [wishC.WishId, wishA.WishId, wishB.WishId]);

        var list = await Repository.GetByMemberAsync(memberId);
        Assert.Equal([wishC.WishId, wishA.WishId, wishB.WishId], list.Select(wish => wish.WishId).ToList());
        Assert.Equal([0, 1, 2], list.Select(wish => wish.Position).ToList());
    }

    [IntegrationFact]
    public async Task DeleteByMember_sweeps_all_wishes_and_only_that_members()
    {
        var memberId = Uid("member");
        var otherMember = Uid("member");
        await CreateTracked(memberId);
        await CreateTracked(memberId, position: 1);
        var kept = await CreateTracked(otherMember);

        await Repository.DeleteByMemberAsync(memberId);

        Assert.Empty(await Repository.GetByMemberAsync(memberId));
        Assert.NotNull(await Repository.GetAsync(otherMember, kept.WishId));
    }
}
