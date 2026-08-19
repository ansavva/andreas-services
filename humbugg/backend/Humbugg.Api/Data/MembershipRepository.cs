using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Models;
using System.Security.Cryptography;
using System.Text;

namespace Humbugg.Api.Data;

internal interface IMembershipRepository
{
    Task<MembershipRecord?> GetAsync(string memberId, CancellationToken cancellationToken = default);
    Task<IReadOnlyList<MembershipRecord>> GetByUserAsync(string userId, CancellationToken cancellationToken = default);
    Task<IReadOnlyList<MembershipRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default);
    Task<MembershipRecord?> GetByUserAndGroupAsync(string userId, string groupId, CancellationToken cancellationToken = default);
    Task<MembershipRecord> CreateAsync(string groupId, string userId, string displayName, bool organizer, CancellationToken cancellationToken = default);
    Task<MembershipRecord> UpdatePrivateAsync(string memberId, string wishlist, string avoidances, Address address, CancellationToken cancellationToken = default);
    Task<MembershipRecord> UpdateParticipationAsync(string memberId, bool participating, CancellationToken cancellationToken = default);
    Task AnonymizeAsync(string memberId, string pseudonym, string displayName, CancellationToken cancellationToken = default);
    Task DeleteAsync(string memberId, CancellationToken cancellationToken = default);
    Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default);
}

internal sealed class MembershipRepository(IAmazonDynamoDB db, HumbuggSettings settings) : IMembershipRepository
{
    public async Task<MembershipRecord?> GetAsync(string memberId, CancellationToken cancellationToken = default)
    {
        var response = await db.GetItemAsync(new GetItemRequest
        {
            TableName = settings.GroupMembersTable,
            Key = new() { ["member_id"] = DynamoValues.S(memberId) },
            ConsistentRead = true
        }, cancellationToken);
        return response.IsItemSet ? Read(response.Item) : null;
    }

    public Task<IReadOnlyList<MembershipRecord>> GetByUserAsync(string userId, CancellationToken cancellationToken = default) =>
        QueryAsync("user_id-index", "user_id", userId, cancellationToken);

    public Task<IReadOnlyList<MembershipRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default) =>
        QueryAsync("group_id-index", "group_id", groupId, cancellationToken);

    public Task<MembershipRecord?> GetByUserAndGroupAsync(string userId, string groupId, CancellationToken cancellationToken = default) =>
        GetAsync(MemberId(groupId, userId), cancellationToken);

    private async Task<IReadOnlyList<MembershipRecord>> QueryAsync(string index, string key, string value, CancellationToken cancellationToken)
    {
        var response = await db.QueryAsync(new QueryRequest
        {
            TableName = settings.GroupMembersTable,
            IndexName = index,
            KeyConditionExpression = "#key = :value",
            ExpressionAttributeNames = new() { ["#key"] = key },
            ExpressionAttributeValues = new() { [":value"] = DynamoValues.S(value) }
        }, cancellationToken);
        return response.Items.Select(Read).ToList();
    }

    public async Task<MembershipRecord> CreateAsync(string groupId, string userId, string displayName, bool organizer, CancellationToken cancellationToken = default)
    {
        var record = NewRecord(groupId, userId, displayName, organizer);
        await db.PutItemAsync(new PutItemRequest
        {
            TableName = settings.GroupMembersTable,
            Item = Write(record),
            ConditionExpression = "attribute_not_exists(member_id)"
        }, cancellationToken);
        return record;
    }

    public Task<MembershipRecord> UpdatePrivateAsync(string memberId, string wishlist, string avoidances, Address address, CancellationToken cancellationToken = default) =>
        UpdateAsync(memberId, "SET wishlist = :wishlist, avoidances = :avoidances, address = :address, updated_at = :now",
            new() { [":wishlist"] = DynamoValues.S(wishlist), [":avoidances"] = DynamoValues.S(avoidances), [":address"] = DynamoValues.AddressValue(address) }, cancellationToken);

    public Task<MembershipRecord> UpdateParticipationAsync(string memberId, bool participating, CancellationToken cancellationToken = default) =>
        UpdateAsync(memberId, "SET is_participating = :participating, updated_at = :now",
            new() { [":participating"] = DynamoValues.B(participating) }, cancellationToken);

    private async Task<MembershipRecord> UpdateAsync(string memberId, string expression, Dictionary<string, AttributeValue> values, CancellationToken cancellationToken)
    {
        values[":now"] = DynamoValues.S(DateTimeOffset.UtcNow.ToString("O"));
        var response = await db.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = settings.GroupMembersTable,
            Key = new() { ["member_id"] = DynamoValues.S(memberId) },
            UpdateExpression = expression,
            ExpressionAttributeValues = values,
            ConditionExpression = "attribute_exists(member_id)",
            ReturnValues = ReturnValue.ALL_NEW
        }, cancellationToken);
        return Read(response.Attributes);
    }

    // Strips the participant's product-profile data (name, wishlist, avoidances, address) and moves
    // the row off the real Cognito subject onto an irreversible pseudonym, while keeping member_id so
    // a completed draw that references it stays valid. Re-pointing user_id also makes account deletion
    // idempotent: a retried deletion no longer finds the row through the user_id GSI.
    public async Task AnonymizeAsync(string memberId, string pseudonym, string displayName, CancellationToken cancellationToken = default)
    {
        await db.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = settings.GroupMembersTable,
            Key = new() { ["member_id"] = DynamoValues.S(memberId) },
            UpdateExpression = "SET user_id = :user, display_name = :name, wishlist = :empty, avoidances = :empty, address = :address, updated_at = :now",
            ExpressionAttributeValues = new()
            {
                [":user"] = DynamoValues.S(pseudonym),
                [":name"] = DynamoValues.S(displayName),
                [":empty"] = DynamoValues.S(""),
                [":address"] = DynamoValues.AddressValue(new Address()),
                [":now"] = DynamoValues.S(DateTimeOffset.UtcNow.ToString("O"))
            },
            ConditionExpression = "attribute_exists(member_id)"
        }, cancellationToken);
    }

    public Task DeleteAsync(string memberId, CancellationToken cancellationToken = default) => db.DeleteItemAsync(
        settings.GroupMembersTable, new Dictionary<string, AttributeValue> { ["member_id"] = DynamoValues.S(memberId) }, cancellationToken);

    public async Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default)
    {
        foreach (var batch in (await GetByGroupAsync(groupId, cancellationToken)).Chunk(25))
        {
            var pending = new Dictionary<string, List<WriteRequest>>
            {
                [settings.GroupMembersTable] = batch.Select(item => new WriteRequest(new DeleteRequest(
                    new Dictionary<string, AttributeValue> { ["member_id"] = DynamoValues.S(item.MemberId) }))).ToList()
            };
            for (var attempt = 0; pending.Count > 0; attempt++)
            {
                if (attempt == 6) throw new InvalidOperationException("DynamoDB did not complete the group-member deletion batch.");
                var response = await db.BatchWriteItemAsync(new BatchWriteItemRequest { RequestItems = pending }, cancellationToken);
                pending = response.UnprocessedItems;
                if (pending.Count > 0) await Task.Delay(TimeSpan.FromMilliseconds(50 * (attempt + 1)), cancellationToken);
            }
        }
    }

    internal static Dictionary<string, AttributeValue> Write(MembershipRecord record) => new()
    {
        ["member_id"] = DynamoValues.S(record.MemberId),
        ["group_id"] = DynamoValues.S(record.GroupId),
        ["user_id"] = DynamoValues.S(record.UserId),
        ["display_name"] = DynamoValues.S(record.DisplayName),
        ["is_organizer"] = DynamoValues.B(record.IsOrganizer),
        ["is_participating"] = DynamoValues.B(record.IsParticipating),
        ["wishlist"] = DynamoValues.S(record.Wishlist),
        ["avoidances"] = DynamoValues.S(record.Avoidances),
        ["address"] = DynamoValues.AddressValue(record.Address),
        ["created_at"] = DynamoValues.S(record.CreatedAt),
        ["updated_at"] = DynamoValues.S(record.UpdatedAt)
    };

    private static MembershipRecord Read(IReadOnlyDictionary<string, AttributeValue> item) => new(
        item.String("member_id"), item.String("group_id"), item.String("user_id"), item.String("display_name"),
        item.Bool("is_organizer"), item.Bool("is_participating"), item.String("wishlist"), item.String("avoidances"),
        item.Address("address"), item.String("created_at"), item.String("updated_at"));

    internal static MembershipRecord NewRecord(
        string groupId,
        string userId,
        string displayName,
        bool organizer,
        bool participating = true)
    {
        var now = DateTimeOffset.UtcNow.ToString("O");
        return new MembershipRecord(
            MemberId(groupId, userId),
            groupId,
            userId,
            displayName,
            organizer,
            participating,
            "",
            "",
            new(),
            now,
            now);
    }

    private static string MemberId(string groupId, string userId) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes($"{groupId}:{userId}"))).ToLowerInvariant()[..32];
}
