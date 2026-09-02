using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Models;

namespace Humbugg.Api.Data;

/// <summary>
/// Anonymous question threads (#131).
/// </summary>
/// <remarks>
/// One partition per thread, keyed <c>{groupId}:{drawId}:{recipientMemberId}</c>, holding the
/// control row (<c>#thread</c>) and every message. Listing a conversation is therefore a single
/// Query on a known key, and there is no access pattern anywhere that starts from a giver — which is
/// what lets the schema omit the giver entirely.
///
/// The one GSI is on <c>group_id</c>, and it exists for deletion rather than for reading: a group
/// that is deleted, a participant who is removed and an account that is erased all have to take
/// these rows with them, and none of them knows which draw ids ever existed.
/// </remarks>
internal interface IQuestionRepository
{
    Task<(QuestionThreadRecord? Thread, IReadOnlyList<QuestionMessageRecord> Messages)> GetThreadAsync(
        string threadId,
        CancellationToken cancellationToken = default);
    Task AppendAsync(QuestionMessageRecord message, CancellationToken cancellationToken = default);
    Task SetBlockedAsync(QuestionThreadRecord thread, CancellationToken cancellationToken = default);
    /// <summary>Deletes every thread in a group — both control rows and messages.</summary>
    Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default);
    /// <summary>Deletes every thread in a group that names this member as either party.</summary>
    Task DeleteForMemberAsync(
        string groupId,
        string recipientMemberId,
        IReadOnlyCollection<string> alsoThreadIds,
        CancellationToken cancellationToken = default);
}

internal sealed class QuestionRepository(IAmazonDynamoDB db, HumbuggSettings settings) : IQuestionRepository
{
    /// <summary>The control row's sort key. Not a valid message id, which begins with a digit.</summary>
    internal const string ThreadSortKey = "#thread";

    public static string ThreadId(string groupId, string drawId, string recipientMemberId) =>
        $"{groupId}:{drawId}:{recipientMemberId}";

    public async Task<(QuestionThreadRecord? Thread, IReadOnlyList<QuestionMessageRecord> Messages)> GetThreadAsync(
        string threadId,
        CancellationToken cancellationToken = default)
    {
        QuestionThreadRecord? thread = null;
        var messages = new List<QuestionMessageRecord>();
        Dictionary<string, AttributeValue>? startKey = null;
        do
        {
            var response = await db.QueryAsync(new QueryRequest
            {
                TableName = settings.QuestionsTable,
                KeyConditionExpression = "thread_id = :thread",
                ExpressionAttributeValues = new() { [":thread"] = DynamoValues.S(threadId) },
                ExclusiveStartKey = startKey,
                // A reply must see the message it is replying to, and the send limit is counted off
                // this read, so a stale page would let a thread run past its cap.
                ConsistentRead = true,
            }, cancellationToken);
            foreach (var item in response.Items)
            {
                if (item.String("message_id") == ThreadSortKey) thread = ReadThread(item);
                else messages.Add(ReadMessage(item));
            }
            startKey = response.LastEvaluatedKey is { Count: > 0 } last ? last : null;
        }
        while (startKey is not null);

        // The sort key is timestamp-prefixed, so Query already returns them in order; sorting again
        // costs nothing and keeps the guarantee local to the one place that reads them.
        messages.Sort((left, right) => string.CompareOrdinal(left.MessageId, right.MessageId));
        return (thread, messages);
    }

    public Task AppendAsync(QuestionMessageRecord message, CancellationToken cancellationToken = default) =>
        db.PutItemAsync(new PutItemRequest
        {
            TableName = settings.QuestionsTable,
            Item = WriteMessage(message),
            ConditionExpression = "attribute_not_exists(message_id)",
        }, cancellationToken);

    public Task SetBlockedAsync(QuestionThreadRecord thread, CancellationToken cancellationToken = default) =>
        db.PutItemAsync(new PutItemRequest
        {
            TableName = settings.QuestionsTable,
            Item = WriteThread(thread),
        }, cancellationToken);

    public async Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default) =>
        await DeleteAsync(await KeysForGroupAsync(groupId, cancellationToken), cancellationToken);

    public async Task DeleteForMemberAsync(
        string groupId,
        string recipientMemberId,
        IReadOnlyCollection<string> alsoThreadIds,
        CancellationToken cancellationToken = default)
    {
        var wanted = new HashSet<string>(alsoThreadIds, StringComparer.Ordinal);
        var keys = (await KeysForGroupAsync(groupId, cancellationToken))
            .Where(key => key.RecipientMemberId == recipientMemberId || wanted.Contains(key.ThreadId))
            .ToList();
        await DeleteAsync(keys, cancellationToken);
    }

    private sealed record RowKey(string ThreadId, string MessageId, string RecipientMemberId);

    private async Task<IReadOnlyList<RowKey>> KeysForGroupAsync(string groupId, CancellationToken cancellationToken)
    {
        var keys = new List<RowKey>();
        Dictionary<string, AttributeValue>? startKey = null;
        do
        {
            var response = await db.QueryAsync(new QueryRequest
            {
                TableName = settings.QuestionsTable,
                IndexName = "group_id-index",
                KeyConditionExpression = "group_id = :group",
                ExpressionAttributeValues = new() { [":group"] = DynamoValues.S(groupId) },
                // Only what a delete needs. The bodies are the whole point of not reading them.
                ProjectionExpression = "thread_id, message_id, recipient_member_id",
                ExclusiveStartKey = startKey,
            }, cancellationToken);
            keys.AddRange(response.Items.Select(item => new RowKey(
                item.String("thread_id"), item.String("message_id"), item.String("recipient_member_id"))));
            startKey = response.LastEvaluatedKey is { Count: > 0 } last ? last : null;
        }
        while (startKey is not null);
        return keys;
    }

    private async Task DeleteAsync(IReadOnlyList<RowKey> keys, CancellationToken cancellationToken)
    {
        foreach (var batch in keys.Chunk(25))
        {
            var pending = new Dictionary<string, List<WriteRequest>>
            {
                [settings.QuestionsTable] = batch
                    .Select(key => new WriteRequest(new DeleteRequest(Key(key.ThreadId, key.MessageId))))
                    .ToList(),
            };
            for (var attempt = 0; pending.Count > 0; attempt++)
            {
                if (attempt == 6)
                    throw new InvalidOperationException("DynamoDB did not complete the question-thread deletion batch.");
                var response = await db.BatchWriteItemAsync(new BatchWriteItemRequest { RequestItems = pending }, cancellationToken);
                pending = response.UnprocessedItems;
                if (pending.Count > 0) await Task.Delay(TimeSpan.FromMilliseconds(50 * (attempt + 1)), cancellationToken);
            }
        }
    }

    private static Dictionary<string, AttributeValue> Key(string threadId, string messageId) => new()
    {
        ["thread_id"] = DynamoValues.S(threadId),
        ["message_id"] = DynamoValues.S(messageId),
    };

    private static Dictionary<string, AttributeValue> WriteMessage(QuestionMessageRecord record) => new(StringComparer.Ordinal)
    {
        ["thread_id"] = DynamoValues.S(record.ThreadId),
        ["message_id"] = DynamoValues.S(record.MessageId),
        ["group_id"] = DynamoValues.S(record.GroupId),
        ["draw_id"] = DynamoValues.S(record.DrawId),
        ["recipient_member_id"] = DynamoValues.S(record.RecipientMemberId),
        // A side, never a person. There is no author_member_id on this row and there must not be.
        ["author"] = DynamoValues.S(record.Author.ToString()),
        ["body"] = DynamoValues.S(record.Body),
        ["created_at"] = DynamoValues.S(record.CreatedAt),
    };

    private static Dictionary<string, AttributeValue> WriteThread(QuestionThreadRecord record) => new(StringComparer.Ordinal)
    {
        ["thread_id"] = DynamoValues.S(record.ThreadId),
        ["message_id"] = DynamoValues.S(ThreadSortKey),
        ["group_id"] = DynamoValues.S(record.GroupId),
        ["recipient_member_id"] = DynamoValues.S(record.RecipientMemberId),
        ["blocked"] = DynamoValues.B(record.Blocked),
        ["updated_at"] = DynamoValues.S(record.UpdatedAt),
    };

    private static QuestionMessageRecord ReadMessage(IReadOnlyDictionary<string, AttributeValue> item) => new(
        item.String("thread_id"),
        item.String("message_id"),
        item.String("group_id"),
        item.String("draw_id"),
        item.String("recipient_member_id"),
        Enum.TryParse<QuestionAuthor>(item.String("author"), out var author) ? author : QuestionAuthor.Giver,
        item.String("body"),
        item.String("created_at"));

    private static QuestionThreadRecord ReadThread(IReadOnlyDictionary<string, AttributeValue> item) => new(
        item.String("thread_id"),
        item.String("group_id"),
        item.String("recipient_member_id"),
        item.Bool("blocked"),
        item.String("updated_at"));
}
