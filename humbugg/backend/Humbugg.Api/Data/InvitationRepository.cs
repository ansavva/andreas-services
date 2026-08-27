using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Models;

namespace Humbugg.Api.Data;

internal interface IInvitationRepository
{
    Task CreateAsync(InvitationRecord value, CancellationToken cancellationToken = default);
    Task<InvitationRecord?> GetAsync(string invitationId, CancellationToken cancellationToken = default);
    Task<IReadOnlyList<InvitationRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default);
    Task UpdateAsync(string invitationId, string status, string? tokenHash, string? expiresAt, string? messageId, CancellationToken cancellationToken = default);
    Task AcceptAndCreateMembershipAsync(
        string invitationId,
        string userId,
        MembershipRecord membership,
        CancellationToken cancellationToken = default);
    Task<string?> GetDeliveryStatusAsync(string? messageId, CancellationToken cancellationToken = default);
}

internal sealed class InvitationRepository(IAmazonDynamoDB db, HumbuggSettings settings) : IInvitationRepository
{
    public Task CreateAsync(InvitationRecord value, CancellationToken cancellationToken = default) =>
        db.PutItemAsync(new PutItemRequest { TableName = settings.InvitationsTable, Item = Write(value), ConditionExpression = "attribute_not_exists(invitation_id)" }, cancellationToken);

    public async Task<InvitationRecord?> GetAsync(string id, CancellationToken cancellationToken = default)
    {
        var response = await db.GetItemAsync(new GetItemRequest { TableName = settings.InvitationsTable, Key = new() { ["invitation_id"] = DynamoValues.S(id) }, ConsistentRead = true }, cancellationToken);
        return response.IsItemSet ? Read(response.Item) : null;
    }

    public async Task<IReadOnlyList<InvitationRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var response = await db.QueryAsync(new QueryRequest { TableName = settings.InvitationsTable, IndexName = "group_id-index", KeyConditionExpression = "group_id = :g", ExpressionAttributeValues = new() { [":g"] = DynamoValues.S(groupId) } }, cancellationToken);
        return response.Items.Select(Read).ToList();
    }

    public Task UpdateAsync(string id, string status, string? tokenHash, string? expiresAt, string? messageId, CancellationToken cancellationToken = default)
    {
        var now = DateTimeOffset.UtcNow.ToString("O");
        var names = new Dictionary<string, string> { ["#s"] = "status" };
        var values = new Dictionary<string, AttributeValue> { [":s"] = DynamoValues.S(status), [":now"] = DynamoValues.S(now) };
        var sets = new List<string> { "#s = :s", "updated_at = :now" };
        if (tokenHash is not null) { sets.Add("token_hash = :t"); values[":t"] = DynamoValues.S(tokenHash); }
        if (expiresAt is not null) { sets.Add("expires_at = :e"); values[":e"] = DynamoValues.S(expiresAt); }
        if (messageId is not null) { sets.Add("message_id = :m"); sets.Add("last_sent_at = :now"); values[":m"] = DynamoValues.S(messageId); }
        return db.UpdateItemAsync(new UpdateItemRequest { TableName = settings.InvitationsTable, Key = new() { ["invitation_id"] = DynamoValues.S(id) }, UpdateExpression = $"SET {string.Join(", ", sets)}", ConditionExpression = "attribute_exists(invitation_id) AND #s <> :accepted AND #s <> :revoked", ExpressionAttributeNames = names, ExpressionAttributeValues = new(values) { [":accepted"] = DynamoValues.S("accepted"), [":revoked"] = DynamoValues.S("revoked") } }, cancellationToken);
    }

    public Task AcceptAndCreateMembershipAsync(
        string id,
        string userId,
        MembershipRecord membership,
        CancellationToken cancellationToken = default)
    {
        var now = DateTimeOffset.UtcNow.ToString("O");
        return db.TransactWriteItemsAsync(new TransactWriteItemsRequest
        {
            TransactItems =
            [
                new()
                {
                    Update = new Update
                    {
                        TableName = settings.InvitationsTable,
                        Key = new() { ["invitation_id"] = DynamoValues.S(id) },
                        UpdateExpression = "SET #s = :accepted, accepted_at = :now, accepted_user_id = :u, updated_at = :now",
                        ConditionExpression = "#s = :sent AND expires_at > :now",
                        ExpressionAttributeNames = new() { ["#s"] = "status" },
                        ExpressionAttributeValues = new()
                        {
                            [":accepted"] = DynamoValues.S("accepted"),
                            [":sent"] = DynamoValues.S("sent"),
                            [":now"] = DynamoValues.S(now),
                            [":u"] = DynamoValues.S(userId)
                        }
                    }
                },
                new()
                {
                    Put = new Put
                    {
                        TableName = settings.GroupMembersTable,
                        Item = MembershipRepository.Write(membership),
                        ConditionExpression = "attribute_not_exists(member_id)"
                    }
                }
            ]
        }, cancellationToken);
    }
    public async Task<string?> GetDeliveryStatusAsync(string? messageId, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(messageId)) return null;
        var response = await db.GetItemAsync(new GetItemRequest { TableName = settings.EmailMessagesTable, Key = new() { ["message_id"] = DynamoValues.S(messageId) } }, cancellationToken);
        return response.IsItemSet ? response.Item.String("status") : null;
    }

    internal static Dictionary<string, AttributeValue> Write(InvitationRecord x)
    {
        var item = new Dictionary<string, AttributeValue>
        {
            ["invitation_id"] = DynamoValues.S(x.InvitationId),
            ["group_id"] = DynamoValues.S(x.GroupId),
            ["email"] = DynamoValues.S(x.Email),
            ["token_hash"] = DynamoValues.S(x.TokenHash),
            ["status"] = DynamoValues.S(x.Status),
            ["expires_at"] = DynamoValues.S(x.ExpiresAt),
            ["created_at"] = DynamoValues.S(x.CreatedAt),
            ["updated_at"] = DynamoValues.S(x.UpdatedAt)
        };
        if (x.AcceptedAt is not null) item["accepted_at"] = DynamoValues.S(x.AcceptedAt);
        if (x.AcceptedUserId is not null) item["accepted_user_id"] = DynamoValues.S(x.AcceptedUserId);
        if (x.LastSentAt is not null) item["last_sent_at"] = DynamoValues.S(x.LastSentAt);
        if (x.MessageId is not null) item["message_id"] = DynamoValues.S(x.MessageId);
        return item;
    }
    private static InvitationRecord Read(IReadOnlyDictionary<string, AttributeValue> x) => new(
        x.String("invitation_id"), x.String("group_id"), x.String("email"), x.String("token_hash"), x.String("status"),
        x.String("expires_at"), x.String("created_at"), x.String("updated_at"), Optional(x, "accepted_at"), Optional(x, "accepted_user_id"), Optional(x, "last_sent_at"), Optional(x, "message_id"));
    private static string? Optional(IReadOnlyDictionary<string, AttributeValue> x, string k) => x.TryGetValue(k, out var v) && v.NULL != true && !string.IsNullOrWhiteSpace(v.S) ? v.S : null;
}
