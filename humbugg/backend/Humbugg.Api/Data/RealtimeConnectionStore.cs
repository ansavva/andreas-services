using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using System.Collections.Concurrent;

namespace Humbugg.Api.Data;

/// <summary>
/// Who is connected to the realtime channel, and the one-time tickets that let them connect (#691).
/// </summary>
/// <remarks>
/// One table, two kinds of row, both short-lived. A CONNECTION row maps an API Gateway connection id
/// to the user holding it, so a nudge for a user can find their sockets. A TICKET row is minted by an
/// authorized HTTP call and consumed — read and deleted in one conditional write — by the
/// <c>$connect</c> authorizer, so the access token never travels in a URL: what does is a random
/// value that is useless after sixty seconds or one use, whichever comes first.
///
/// Rows are keyed by USER, never by who gives to whom. Nothing about the draw lives here.
/// </remarks>
internal interface IRealtimeConnectionStore
{
    Task PutTicketAsync(string ticket, string userId, DateTimeOffset expiresAt, CancellationToken cancellationToken = default);

    /// <summary>The user the ticket was minted for, deleting it; null when unknown, spent or expired.</summary>
    Task<string?> ConsumeTicketAsync(string ticket, DateTimeOffset now, CancellationToken cancellationToken = default);

    Task PutConnectionAsync(string connectionId, string userId, DateTimeOffset expiresAt, CancellationToken cancellationToken = default);

    Task RemoveConnectionAsync(string connectionId, CancellationToken cancellationToken = default);

    Task<IReadOnlyList<string>> ConnectionsForUserAsync(string userId, CancellationToken cancellationToken = default);
}

internal sealed class DynamoDbRealtimeConnectionStore(IAmazonDynamoDB db, string tableName) : IRealtimeConnectionStore
{
    internal const string UserIndex = "user_id-index";
    private const string TicketPrefix = "ticket#";

    public Task PutTicketAsync(string ticket, string userId, DateTimeOffset expiresAt, CancellationToken cancellationToken = default) =>
        db.PutItemAsync(new PutItemRequest
        {
            TableName = tableName,
            Item = new Dictionary<string, AttributeValue>(StringComparer.Ordinal)
            {
                ["connection_id"] = DynamoValues.S(TicketPrefix + ticket),
                ["user_id"] = DynamoValues.S(userId),
                ["kind"] = DynamoValues.S("ticket"),
                ["expires_at"] = DynamoValues.N(expiresAt.ToUnixTimeSeconds())
            },
            ConditionExpression = "attribute_not_exists(connection_id)"
        }, cancellationToken);

    public async Task<string?> ConsumeTicketAsync(string ticket, DateTimeOffset now, CancellationToken cancellationToken = default)
    {
        try
        {
            // Delete-with-return is the single use: two connects racing on one ticket cannot both win.
            // The TTL sweeper lags by minutes, so expiry is checked here rather than trusted to it.
            var response = await db.DeleteItemAsync(new DeleteItemRequest
            {
                TableName = tableName,
                Key = new Dictionary<string, AttributeValue> { ["connection_id"] = DynamoValues.S(TicketPrefix + ticket) },
                ConditionExpression = "attribute_exists(connection_id) AND expires_at > :now",
                ExpressionAttributeValues = new Dictionary<string, AttributeValue> { [":now"] = DynamoValues.N(now.ToUnixTimeSeconds()) },
                ReturnValues = ReturnValue.ALL_OLD
            }, cancellationToken);
            var userId = response.Attributes is null ? "" : ((IReadOnlyDictionary<string, AttributeValue>)response.Attributes).String("user_id");
            return string.IsNullOrEmpty(userId) ? null : userId;
        }
        catch (ConditionalCheckFailedException)
        {
            return null;
        }
    }

    public Task PutConnectionAsync(string connectionId, string userId, DateTimeOffset expiresAt, CancellationToken cancellationToken = default) =>
        db.PutItemAsync(new PutItemRequest
        {
            TableName = tableName,
            Item = new Dictionary<string, AttributeValue>(StringComparer.Ordinal)
            {
                ["connection_id"] = DynamoValues.S(connectionId),
                ["user_id"] = DynamoValues.S(userId),
                ["kind"] = DynamoValues.S("connection"),
                ["expires_at"] = DynamoValues.N(expiresAt.ToUnixTimeSeconds())
            }
        }, cancellationToken);

    public Task RemoveConnectionAsync(string connectionId, CancellationToken cancellationToken = default) =>
        db.DeleteItemAsync(new DeleteItemRequest
        {
            TableName = tableName,
            Key = new Dictionary<string, AttributeValue> { ["connection_id"] = DynamoValues.S(connectionId) }
        }, cancellationToken);

    public async Task<IReadOnlyList<string>> ConnectionsForUserAsync(string userId, CancellationToken cancellationToken = default)
    {
        var ids = new List<string>();
        Dictionary<string, AttributeValue>? start = null;
        do
        {
            var response = await db.QueryAsync(new QueryRequest
            {
                TableName = tableName,
                IndexName = UserIndex,
                KeyConditionExpression = "user_id = :user",
                ExpressionAttributeValues = new Dictionary<string, AttributeValue> { [":user"] = DynamoValues.S(userId) },
                ExclusiveStartKey = start
            }, cancellationToken);
            // Tickets share the index; only connections can be posted to.
            ids.AddRange(response.Items
                .Select(item => ((IReadOnlyDictionary<string, AttributeValue>)item).String("connection_id"))
                .Where(id => id.Length > 0 && !id.StartsWith(TicketPrefix, StringComparison.Ordinal)));
            start = response.LastEvaluatedKey is { Count: > 0 } ? response.LastEvaluatedKey : null;
        }
        while (start is not null);
        return ids;
    }
}

/// <summary>
/// The same contract in memory — the dev container, which hosts its own sockets, and the tests.
/// </summary>
internal sealed class InMemoryRealtimeConnectionStore : IRealtimeConnectionStore
{
    private readonly ConcurrentDictionary<string, (string UserId, DateTimeOffset ExpiresAt)> tickets = new(StringComparer.Ordinal);
    private readonly ConcurrentDictionary<string, string> connections = new(StringComparer.Ordinal);

    public Task PutTicketAsync(string ticket, string userId, DateTimeOffset expiresAt, CancellationToken cancellationToken = default)
    {
        tickets[ticket] = (userId, expiresAt);
        return Task.CompletedTask;
    }

    public Task<string?> ConsumeTicketAsync(string ticket, DateTimeOffset now, CancellationToken cancellationToken = default)
    {
        if (!tickets.TryRemove(ticket, out var entry)) return Task.FromResult<string?>(null);
        return Task.FromResult(entry.ExpiresAt > now ? entry.UserId : null);
    }

    public Task PutConnectionAsync(string connectionId, string userId, DateTimeOffset expiresAt, CancellationToken cancellationToken = default)
    {
        connections[connectionId] = userId;
        return Task.CompletedTask;
    }

    public Task RemoveConnectionAsync(string connectionId, CancellationToken cancellationToken = default)
    {
        connections.TryRemove(connectionId, out _);
        return Task.CompletedTask;
    }

    public Task<IReadOnlyList<string>> ConnectionsForUserAsync(string userId, CancellationToken cancellationToken = default) =>
        Task.FromResult<IReadOnlyList<string>>(connections.Where(pair => pair.Value == userId).Select(pair => pair.Key).ToList());
}
