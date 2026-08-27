using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Models;

namespace Humbugg.Api.Data;

internal interface IWishRepository
{
    Task<IReadOnlyList<WishRecord>> GetByMemberAsync(string memberId, CancellationToken cancellationToken = default);
    Task<WishRecord?> GetAsync(string memberId, string wishId, CancellationToken cancellationToken = default);
    Task CreateAsync(WishRecord record, CancellationToken cancellationToken = default);
    Task<WishRecord> UpdateAsync(
        string memberId,
        string wishId,
        IReadOnlyDictionary<string, AttributeValue> fields,
        CancellationToken cancellationToken = default);
    Task DeleteAsync(string memberId, string wishId, CancellationToken cancellationToken = default);
    Task DeleteByMemberAsync(string memberId, CancellationToken cancellationToken = default);
    Task SetPositionsAsync(
        string memberId,
        IReadOnlyList<string> orderedWishIds,
        CancellationToken cancellationToken = default);
}

internal sealed class WishRepository(IAmazonDynamoDB db, HumbuggSettings settings) : IWishRepository
{
    // A Query on the partition key. There is no Scan anywhere in this repository, and no index:
    // every access pattern this table has starts from a known member_id.
    public async Task<IReadOnlyList<WishRecord>> GetByMemberAsync(
        string memberId,
        CancellationToken cancellationToken = default)
    {
        var records = new List<WishRecord>();
        Dictionary<string, AttributeValue>? startKey = null;
        do
        {
            var response = await db.QueryAsync(new QueryRequest
            {
                TableName = settings.WishesTable,
                KeyConditionExpression = "member_id = :member",
                ExpressionAttributeValues = new() { [":member"] = DynamoValues.S(memberId) },
                ExclusiveStartKey = startKey
            }, cancellationToken);
            records.AddRange(response.Items.Select(Read));
            startKey = response.LastEvaluatedKey is { Count: > 0 } last ? last : null;
        }
        // A list is capped well below one page, but paginating costs three lines and removes the
        // class of bug where a cap is raised later and reads silently start truncating.
        while (startKey is not null);

        return records.OrderBy(record => record.Position).ThenBy(record => record.CreatedAt, StringComparer.Ordinal).ToList();
    }

    public async Task<WishRecord?> GetAsync(string memberId, string wishId, CancellationToken cancellationToken = default)
    {
        var response = await db.GetItemAsync(new GetItemRequest
        {
            TableName = settings.WishesTable,
            Key = Key(memberId, wishId)
        }, cancellationToken);
        return response.Item is { Count: > 0 } item ? Read(item) : null;
    }

    public Task CreateAsync(WishRecord record, CancellationToken cancellationToken = default) =>
        db.PutItemAsync(new PutItemRequest
        {
            TableName = settings.WishesTable,
            Item = Write(record),
            ConditionExpression = "attribute_not_exists(wish_id)"
        }, cancellationToken);

    // Throws ConditionalCheckFailedException when the wish does not exist under this member, which is
    // the same signal as "not yours": the key carries the owner, so a caller cannot address someone
    // else's wish even by guessing its id.
    public async Task<WishRecord> UpdateAsync(
        string memberId,
        string wishId,
        IReadOnlyDictionary<string, AttributeValue> fields,
        CancellationToken cancellationToken = default)
    {
        var names = new Dictionary<string, string>(StringComparer.Ordinal);
        var values = new Dictionary<string, AttributeValue>(StringComparer.Ordinal);
        var assignments = new List<string>();
        var index = 0;
        foreach (var (field, value) in fields)
        {
            var name = $"#f{index}";
            var placeholder = $":v{index}";
            names[name] = field;
            values[placeholder] = value;
            assignments.Add($"{name} = {placeholder}");
            index++;
        }

        var response = await db.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = settings.WishesTable,
            Key = Key(memberId, wishId),
            UpdateExpression = $"SET {string.Join(", ", assignments)}",
            ExpressionAttributeNames = names,
            ExpressionAttributeValues = values,
            ConditionExpression = "attribute_exists(wish_id)",
            ReturnValues = ReturnValue.ALL_NEW
        }, cancellationToken);
        return Read(response.Attributes);
    }

    public Task DeleteAsync(string memberId, string wishId, CancellationToken cancellationToken = default) =>
        db.DeleteItemAsync(new DeleteItemRequest
        {
            TableName = settings.WishesTable,
            Key = Key(memberId, wishId),
            ConditionExpression = "attribute_exists(wish_id)"
        }, cancellationToken);

    // Called when a membership is removed or anonymized. A wish is personal data authored by the
    // member, so it does not survive them (#122, #189) — including the anonymize path, where the
    // membership row must live on because a draw references it but its contents must not.
    public async Task DeleteByMemberAsync(string memberId, CancellationToken cancellationToken = default)
    {
        var records = await GetByMemberAsync(memberId, cancellationToken);
        foreach (var batch in records.Chunk(25))
        {
            await db.BatchWriteItemAsync(new BatchWriteItemRequest
            {
                RequestItems = new()
                {
                    [settings.WishesTable] = batch
                        .Select(record => new WriteRequest(new DeleteRequest(Key(record.MemberId, record.WishId))))
                        .ToList()
                }
            }, cancellationToken);
        }
    }

    // Positions are rewritten as a dense 0..n-1 sequence rather than patched, so a reorder cannot
    // leave duplicates or gaps behind however the caller shuffled the list.
    public async Task SetPositionsAsync(
        string memberId,
        IReadOnlyList<string> orderedWishIds,
        CancellationToken cancellationToken = default)
    {
        var now = DateTimeOffset.UtcNow.ToString("O");
        for (var position = 0; position < orderedWishIds.Count; position++)
        {
            await db.UpdateItemAsync(new UpdateItemRequest
            {
                TableName = settings.WishesTable,
                Key = Key(memberId, orderedWishIds[position]),
                UpdateExpression = "SET #position = :position, updated_at = :updated_at",
                ExpressionAttributeNames = new() { ["#position"] = "position" },
                ExpressionAttributeValues = new()
                {
                    [":position"] = DynamoValues.N(position),
                    [":updated_at"] = DynamoValues.S(now)
                },
                ConditionExpression = "attribute_exists(wish_id)"
            }, cancellationToken);
        }
    }

    private static Dictionary<string, AttributeValue> Key(string memberId, string wishId) => new()
    {
        ["member_id"] = DynamoValues.S(memberId),
        ["wish_id"] = DynamoValues.S(wishId)
    };

    private static Dictionary<string, AttributeValue> Write(WishRecord record)
    {
        var item = new Dictionary<string, AttributeValue>(StringComparer.Ordinal)
        {
            ["member_id"] = DynamoValues.S(record.MemberId),
            ["wish_id"] = DynamoValues.S(record.WishId),
            ["group_id"] = DynamoValues.S(record.GroupId),
            ["user_id"] = DynamoValues.S(record.UserId),
            ["kind"] = DynamoValues.S(record.Kind.ToString()),
            ["title"] = DynamoValues.S(record.Title),
            ["url"] = DynamoValues.S(record.Url),
            ["image_url"] = DynamoValues.S(record.ImageUrl),
            ["currency"] = DynamoValues.S(record.Currency),
            ["quantity"] = DynamoValues.N(record.Quantity),
            ["priority"] = DynamoValues.S(record.Priority.ToString()),
            ["details"] = DynamoValues.S(record.Details),
            ["position"] = DynamoValues.N(record.Position),
            ["created_at"] = DynamoValues.S(record.CreatedAt),
            ["updated_at"] = DynamoValues.S(record.UpdatedAt)
        };
        // Absent rather than zero: a wish with no price is not a wish that costs nothing.
        if (record.PriceCents is { } price) item["price_cents"] = DynamoValues.N(price);
        return item;
    }

    private static WishRecord Read(IReadOnlyDictionary<string, AttributeValue> item) => new(
        item.String("member_id"),
        item.String("wish_id"),
        item.String("group_id"),
        item.String("user_id"),
        Enum.TryParse<WishKind>(item.String("kind"), out var kind) ? kind : WishKind.Custom,
        item.String("title"),
        item.String("url"),
        item.String("image_url"),
        item.Long("price_cents"),
        item.String("currency"),
        (int)(item.Long("quantity") ?? 1),
        Enum.TryParse<WishPriority>(item.String("priority"), out var priority) ? priority : WishPriority.Normal,
        item.String("details"),
        (int)(item.Long("position") ?? 0),
        item.String("created_at"),
        item.String("updated_at"));
}
