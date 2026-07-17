using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Models;
using System.Text.Json;

namespace Humbugg.Api.Data;

/// <summary>
/// Append-only persistence for <see cref="AuditEvent"/> records.
/// The interface exposes no update or delete operation on purpose: audit records are
/// immutable through the application. <see cref="AppendAsync"/> awaits the write and lets
/// any failure propagate, so an audited action cannot silently lose its audit record.
/// </summary>
internal interface IAuditRepository
{
    Task AppendAsync(AuditEvent auditEvent, CancellationToken cancellationToken = default);
}

internal sealed class AuditRepository(IAmazonDynamoDB db, HumbuggSettings settings) : IAuditRepository
{
    public async Task AppendAsync(AuditEvent auditEvent, CancellationToken cancellationToken = default)
    {
        var item = new Dictionary<string, AttributeValue>
        {
            ["group_id"] = DynamoValues.S(auditEvent.GroupId),
            ["event_id"] = DynamoValues.S(auditEvent.EventId),
            ["action"] = DynamoValues.S(Wire(auditEvent.Action)),
            ["actor_user_id"] = DynamoValues.S(auditEvent.ActorUserId),
            ["target_type"] = DynamoValues.S(auditEvent.TargetType),
            ["target_id"] = DynamoValues.S(auditEvent.TargetId),
            ["correlation_id"] = DynamoValues.S(auditEvent.CorrelationId),
            ["created_at"] = DynamoValues.S(auditEvent.CreatedAt)
        };
        if (auditEvent.OrganizationId is not null)
            item["organization_id"] = DynamoValues.S(auditEvent.OrganizationId);
        if (auditEvent.Metadata.Count > 0)
            item["metadata"] = new AttributeValue
            {
                M = auditEvent.Metadata.ToDictionary(pair => pair.Key, pair => DynamoValues.S(pair.Value))
            };

        // attribute_not_exists on the full key makes the write append-only: an existing
        // (group_id, event_id) record can never be overwritten through this path.
        await db.PutItemAsync(new PutItemRequest
        {
            TableName = settings.AuditEventsTable,
            Item = item,
            ConditionExpression = "attribute_not_exists(group_id) AND attribute_not_exists(event_id)"
        }, cancellationToken);
    }

    /// <summary>Serializes the action to the repo's snake_case wire form (e.g. <c>group_created</c>).</summary>
    internal static string Wire(AuditAction action) => JsonNamingPolicy.SnakeCaseLower.ConvertName(action.ToString());
}
