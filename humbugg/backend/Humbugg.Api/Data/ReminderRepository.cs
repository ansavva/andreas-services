using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Models;

namespace Humbugg.Api.Data;

internal interface IReminderRepository
{
    Task<ReminderConfigurationRecord?> GetConfigurationAsync(string groupId, CancellationToken cancellationToken = default);
    Task SaveConfigurationAsync(ReminderConfigurationRecord configuration, CancellationToken cancellationToken = default);
    Task<IReadOnlyList<ReminderConfigurationRecord>> GetDueAsync(string now, CancellationToken cancellationToken = default);
    Task<bool> ClaimAutomaticRunAsync(string groupId, string expectedNext, string next, CancellationToken cancellationToken = default);
    Task<bool> ClaimManualRunAsync(string groupId, string cutoff, string now, CancellationToken cancellationToken = default);
    Task SaveHistoryAsync(string groupId, ReminderHistoryItem item, CancellationToken cancellationToken = default);
    Task<IReadOnlyList<ReminderHistoryItem>> GetHistoryAsync(string groupId, int limit, CancellationToken cancellationToken = default);
}

internal sealed class ReminderRepository(IAmazonDynamoDB db, HumbuggSettings settings) : IReminderRepository
{
    private const string ConfigurationKey = "CONFIG";

    public async Task<ReminderConfigurationRecord?> GetConfigurationAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var response = await db.GetItemAsync(new GetItemRequest
        {
            TableName = settings.RemindersTable,
            Key = Key(groupId, ConfigurationKey),
            ConsistentRead = true
        }, cancellationToken);
        return response.IsItemSet ? ReadConfiguration(response.Item) : null;
    }

    public Task SaveConfigurationAsync(ReminderConfigurationRecord value, CancellationToken cancellationToken = default) =>
        db.PutItemAsync(new PutItemRequest
        {
            TableName = settings.RemindersTable,
            Item = WriteConfiguration(value)
        }, cancellationToken);

    public async Task<IReadOnlyList<ReminderConfigurationRecord>> GetDueAsync(string now, CancellationToken cancellationToken = default)
    {
        var result = new List<ReminderConfigurationRecord>();
        Dictionary<string, AttributeValue>? cursor = null;
        do
        {
            var response = await db.ScanAsync(new ScanRequest
            {
                TableName = settings.RemindersTable,
                ExclusiveStartKey = cursor,
                FilterExpression = "record_key = :config AND #state = :active AND next_scheduled_at <= :now",
                ExpressionAttributeNames = new() { ["#state"] = "state" },
                ExpressionAttributeValues = new()
                {
                    [":config"] = DynamoValues.S(ConfigurationKey),
                    [":active"] = DynamoValues.S("active"),
                    [":now"] = DynamoValues.S(now)
                }
            }, cancellationToken);
            result.AddRange(response.Items.Select(ReadConfiguration));
            cursor = response.LastEvaluatedKey?.Count > 0 ? response.LastEvaluatedKey : null;
        } while (cursor is not null);
        return result;
    }

    public async Task<bool> ClaimAutomaticRunAsync(
        string groupId,
        string expectedNext,
        string next,
        CancellationToken cancellationToken = default)
    {
        try
        {
            await db.UpdateItemAsync(new UpdateItemRequest
            {
                TableName = settings.RemindersTable,
                Key = Key(groupId, ConfigurationKey),
                UpdateExpression = "SET next_scheduled_at = :next, updated_at = :now",
                ConditionExpression = "#state = :active AND next_scheduled_at = :expected",
                ExpressionAttributeNames = new() { ["#state"] = "state" },
                ExpressionAttributeValues = new()
                {
                    [":active"] = DynamoValues.S("active"),
                    [":expected"] = DynamoValues.S(expectedNext),
                    [":next"] = DynamoValues.S(next),
                    [":now"] = DynamoValues.S(DateTimeOffset.UtcNow.ToString("O"))
                }
            }, cancellationToken);
            return true;
        }
        catch (ConditionalCheckFailedException)
        {
            return false;
        }
    }

    public async Task<bool> ClaimManualRunAsync(
        string groupId,
        string cutoff,
        string now,
        CancellationToken cancellationToken = default)
    {
        try
        {
            await db.UpdateItemAsync(new UpdateItemRequest
            {
                TableName = settings.RemindersTable,
                Key = Key(groupId, ConfigurationKey),
                UpdateExpression = "SET last_manual_at = :now, updated_at = :now",
                ConditionExpression = "attribute_exists(group_id) AND (attribute_not_exists(last_manual_at) OR last_manual_at <= :cutoff)",
                ExpressionAttributeValues = new()
                {
                    [":now"] = DynamoValues.S(now),
                    [":cutoff"] = DynamoValues.S(cutoff)
                }
            }, cancellationToken);
            return true;
        }
        catch (ConditionalCheckFailedException)
        {
            return false;
        }
    }

    public Task SaveHistoryAsync(string groupId, ReminderHistoryItem item, CancellationToken cancellationToken = default) =>
        db.PutItemAsync(new PutItemRequest
        {
            TableName = settings.RemindersTable,
            Item = new()
            {
                ["group_id"] = DynamoValues.S(groupId),
                ["record_key"] = DynamoValues.S($"H#{item.CreatedAt}#{item.ReminderId}"),
                ["reminder_id"] = DynamoValues.S(item.ReminderId),
                ["rule"] = DynamoValues.S(Rule(item.Rule)),
                ["invitation_id"] = DynamoValues.S(item.InvitationId),
                ["status"] = DynamoValues.S(item.Status),
                ["created_at"] = DynamoValues.S(item.CreatedAt)
            },
            ConditionExpression = "attribute_not_exists(group_id)"
        }, cancellationToken);

    public async Task<IReadOnlyList<ReminderHistoryItem>> GetHistoryAsync(
        string groupId,
        int limit,
        CancellationToken cancellationToken = default)
    {
        var response = await db.QueryAsync(new QueryRequest
        {
            TableName = settings.RemindersTable,
            KeyConditionExpression = "group_id = :group AND begins_with(record_key, :history)",
            ExpressionAttributeValues = new()
            {
                [":group"] = DynamoValues.S(groupId),
                [":history"] = DynamoValues.S("H#")
            },
            ScanIndexForward = false,
            Limit = limit
        }, cancellationToken);
        return response.Items.Select(ReadHistory).ToList();
    }

    private static Dictionary<string, AttributeValue> Key(string groupId, string recordKey) => new()
    {
        ["group_id"] = DynamoValues.S(groupId),
        ["record_key"] = DynamoValues.S(recordKey)
    };

    private static Dictionary<string, AttributeValue> WriteConfiguration(ReminderConfigurationRecord value) => new()
    {
        ["group_id"] = DynamoValues.S(value.GroupId),
        ["record_key"] = DynamoValues.S(ConfigurationKey),
        ["state"] = DynamoValues.S(value.State.ToString().ToLowerInvariant()),
        ["remind_unaccepted"] = DynamoValues.B(value.RemindUnacceptedInvitations),
        ["remind_readiness"] = DynamoValues.B(value.RemindIncompleteReadiness),
        ["interval_days"] = DynamoValues.N(value.IntervalDays),
        ["quiet_start_utc_hour"] = DynamoValues.N(value.QuietStartUtcHour),
        ["quiet_end_utc_hour"] = DynamoValues.N(value.QuietEndUtcHour),
        ["next_scheduled_at"] = value.NextScheduledAt is null ? new() { NULL = true } : DynamoValues.S(value.NextScheduledAt),
        ["last_manual_at"] = value.LastManualAt is null ? new() { NULL = true } : DynamoValues.S(value.LastManualAt),
        ["updated_at"] = DynamoValues.S(value.UpdatedAt)
    };

    private static ReminderConfigurationRecord ReadConfiguration(IReadOnlyDictionary<string, AttributeValue> item) => new(
        item.String("group_id"),
        Enum.TryParse<ReminderState>(item.String("state"), true, out var state) ? state : ReminderState.Stopped,
        item.Bool("remind_unaccepted"),
        item.Bool("remind_readiness"),
        (int)(item.Long("interval_days") ?? 3),
        (int)(item.Long("quiet_start_utc_hour") ?? 9),
        (int)(item.Long("quiet_end_utc_hour") ?? 20),
        Optional(item, "next_scheduled_at"),
        Optional(item, "last_manual_at"),
        item.String("updated_at"));

    private static ReminderHistoryItem ReadHistory(IReadOnlyDictionary<string, AttributeValue> item) => new(
        item.String("reminder_id"),
        item.String("rule") == "incomplete_readiness" ? ReminderRule.IncompleteReadiness : ReminderRule.UnacceptedInvitation,
        item.String("invitation_id"),
        item.String("status"),
        item.String("created_at"));

    private static string Rule(ReminderRule rule) =>
        rule == ReminderRule.IncompleteReadiness ? "incomplete_readiness" : "unaccepted_invitation";

    private static string? Optional(IReadOnlyDictionary<string, AttributeValue> item, string key) =>
        item.TryGetValue(key, out var value) && value.NULL != true && !string.IsNullOrWhiteSpace(value.S) ? value.S : null;
}
