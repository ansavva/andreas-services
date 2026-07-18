using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Models;
using System.Text.Json;

namespace Humbugg.Api.Data;

/// <summary>
/// The durable destination for analytics events. The interface exposes no update or delete path:
/// analytics records, like audit records, are only ever written. <see cref="RecordAsync"/> is
/// responsible for <b>duplicate control</b> — re-recording an event with an idempotency key that
/// already exists must be a silent no-op, never a second row.
/// </summary>
internal interface IAnalyticsSink
{
    Task RecordAsync(AnalyticsEvent analyticsEvent, CancellationToken cancellationToken = default);
}

/// <summary>
/// Persists analytics events to the <c>humbugg-analytics-events</c> DynamoDB table, keyed by the
/// event's idempotency key. The write uses an <c>attribute_not_exists</c> condition, so a repeated
/// idempotency key is rejected by DynamoDB and swallowed here: retries, double-clicks, and
/// at-least-once redelivery all collapse to a single counted event.
/// </summary>
internal sealed class DynamoDbAnalyticsSink(IAmazonDynamoDB db, HumbuggSettings settings) : IAnalyticsSink
{
    public async Task RecordAsync(AnalyticsEvent analyticsEvent, CancellationToken cancellationToken = default)
    {
        var item = new Dictionary<string, AttributeValue>
        {
            ["idempotency_key"] = DynamoValues.S(analyticsEvent.IdempotencyKey),
            ["event_type"] = DynamoValues.S(Wire(analyticsEvent.EventType)),
            ["plan"] = DynamoValues.S(analyticsEvent.Plan.ToString().ToLowerInvariant()),
            ["group_id"] = DynamoValues.S(analyticsEvent.GroupId),
            ["occurred_at"] = DynamoValues.S(analyticsEvent.OccurredAt)
        };
        if (analyticsEvent.Dimensions.Count > 0)
            item["dimensions"] = new AttributeValue
            {
                M = analyticsEvent.Dimensions.ToDictionary(pair => pair.Key, pair => DynamoValues.S(pair.Value))
            };

        try
        {
            await db.PutItemAsync(new PutItemRequest
            {
                TableName = settings.AnalyticsEventsTable,
                Item = item,
                ConditionExpression = "attribute_not_exists(idempotency_key)"
            }, cancellationToken);
        }
        catch (ConditionalCheckFailedException)
        {
            // Duplicate: the idempotency key was already recorded. Controlling duplicates is the
            // whole point of the conditional write, so this is expected and intentionally ignored.
        }
    }

    /// <summary>Serializes the event type to snake_case wire form (e.g. <c>draw_completed</c>).</summary>
    internal static string Wire(AnalyticsEventType type) => JsonNamingPolicy.SnakeCaseLower.ConvertName(type.ToString());
}
