using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Data;
using Humbugg.Api.Models;

namespace Humbugg.Api.Tests;

/// <summary>
/// An in-memory <see cref="IWishRepository"/> that behaves like the real one rather than recording
/// calls: it enforces the same member_id + wish_id key, so a test asserting that a caller cannot
/// touch another member's wish is testing the same rule production relies on.
/// </summary>
internal sealed class FakeWishes(params WishRecord[] seed) : IWishRepository
{
    private readonly List<WishRecord> items = [.. seed];

    public IReadOnlyList<WishRecord> All => items;

    public Task<IReadOnlyList<WishRecord>> GetByMemberAsync(string memberId, CancellationToken cancellationToken = default) =>
        Task.FromResult<IReadOnlyList<WishRecord>>(items
            .Where(item => item.MemberId == memberId)
            .OrderBy(item => item.Position)
            .ThenBy(item => item.CreatedAt, StringComparer.Ordinal)
            .ToList());

    public Task<WishRecord?> GetAsync(string memberId, string wishId, CancellationToken cancellationToken = default) =>
        Task.FromResult(items.FirstOrDefault(item => item.MemberId == memberId && item.WishId == wishId));

    public Task CreateAsync(WishRecord record, CancellationToken cancellationToken = default)
    {
        items.Add(record);
        return Task.CompletedTask;
    }

    public Task<WishRecord> UpdateAsync(
        string memberId,
        string wishId,
        IReadOnlyDictionary<string, AttributeValue> fields,
        CancellationToken cancellationToken = default)
    {
        var index = items.FindIndex(item => item.MemberId == memberId && item.WishId == wishId);
        // The real repository sets ConditionExpression "attribute_exists(wish_id)" on a key that
        // includes member_id, so a miss here is the same signal production gives.
        if (index < 0) throw new ConditionalCheckFailedException("no such wish");

        var record = items[index];
        foreach (var (field, value) in fields)
        {
            record = field switch
            {
                "kind" => record with { Kind = Enum.Parse<WishKind>(value.S) },
                "title" => record with { Title = value.S },
                "url" => record with { Url = value.S },
                "image_url" => record with { ImageUrl = value.S },
                "currency" => record with { Currency = value.S },
                "quantity" => record with { Quantity = int.Parse(value.N) },
                "priority" => record with { Priority = Enum.Parse<WishPriority>(value.S) },
                "details" => record with { Details = value.S },
                "price_cents" => record with { PriceCents = long.Parse(value.N) },
                "position" => record with { Position = int.Parse(value.N) },
                "updated_at" => record with { UpdatedAt = value.S },
                _ => record
            };
        }
        items[index] = record;
        return Task.FromResult(record);
    }

    public Task DeleteAsync(string memberId, string wishId, CancellationToken cancellationToken = default)
    {
        var index = items.FindIndex(item => item.MemberId == memberId && item.WishId == wishId);
        if (index < 0) throw new ConditionalCheckFailedException("no such wish");
        items.RemoveAt(index);
        return Task.CompletedTask;
    }

    public Task DeleteByMemberAsync(string memberId, CancellationToken cancellationToken = default)
    {
        items.RemoveAll(item => item.MemberId == memberId);
        return Task.CompletedTask;
    }

    public Task SetPositionsAsync(
        string memberId,
        IReadOnlyList<string> orderedWishIds,
        CancellationToken cancellationToken = default)
    {
        for (var position = 0; position < orderedWishIds.Count; position++)
        {
            var index = items.FindIndex(item => item.MemberId == memberId && item.WishId == orderedWishIds[position]);
            if (index < 0) throw new ConditionalCheckFailedException("no such wish");
            items[index] = items[index] with { Position = position };
        }
        return Task.CompletedTask;
    }

    public static WishRecord Record(
        string memberId,
        string wishId,
        string title = "A thing",
        int position = 0,
        WishKind kind = WishKind.Product) => new(
        memberId, wishId, "group", $"user-{memberId}", kind, title,
        Url: "", ImageUrl: "", PriceCents: null, Currency: "USD", Quantity: 1,
        Priority: WishPriority.Normal, Details: "", Position: position,
        CreatedAt: "2026-01-01T00:00:00.0000000+00:00",
        UpdatedAt: "2026-01-01T00:00:00.0000000+00:00");
}
