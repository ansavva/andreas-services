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

/// <summary>
/// The single, deliberately narrow maintenance path that may mutate an existing audit record.
/// It exists only to satisfy an individual's right to erasure: on account deletion the actor's
/// Cognito subject is replaced with an irreversible pseudonym across every record they authored.
/// <para>
/// This is intentionally NOT part of <see cref="IAuditRepository"/>, which stays append-only.
/// Anonymization never deletes a record and never touches the action, target, scope, timestamp,
/// correlation id, or metadata — the audit trail (what happened, to what, when) stays intact.
/// Only the actor identifier is rewritten, and rewriting to the same pseudonym twice is a no-op,
/// so the operation is safe to retry.
/// </para>
/// </summary>
internal interface IAuditActorAnonymizer
{
    /// <summary>
    /// Rewrites <c>actor_user_id</c> from <paramref name="userId"/> to <paramref name="pseudonym"/>
    /// on every audit record authored by that user. Returns the number of records rewritten.
    /// </summary>
    Task<int> AnonymizeActorAsync(string userId, string pseudonym, CancellationToken cancellationToken = default);
}

internal sealed class AuditActorAnonymizer(IAmazonDynamoDB db, HumbuggSettings settings) : IAuditActorAnonymizer
{
    public async Task<int> AnonymizeActorAsync(string userId, string pseudonym, CancellationToken cancellationToken = default)
    {
        if (string.Equals(userId, pseudonym, StringComparison.Ordinal)) return 0;
        var rewritten = 0;
        Dictionary<string, AttributeValue>? lastKey = null;
        do
        {
            var scan = await db.ScanAsync(new ScanRequest
            {
                TableName = settings.AuditEventsTable,
                FilterExpression = "actor_user_id = :actor",
                ExpressionAttributeValues = new Dictionary<string, AttributeValue> { [":actor"] = DynamoValues.S(userId) },
                ProjectionExpression = "group_id, event_id",
                ExclusiveStartKey = lastKey
            }, cancellationToken);
            foreach (var item in scan.Items)
            {
                // Condition keeps the rewrite idempotent and append-only-safe: it only ever moves the
                // actor off the real subject, never overwrites an already-anonymized (or any other) value.
                await db.UpdateItemAsync(new UpdateItemRequest
                {
                    TableName = settings.AuditEventsTable,
                    Key = new Dictionary<string, AttributeValue>
                    {
                        ["group_id"] = item["group_id"],
                        ["event_id"] = item["event_id"]
                    },
                    UpdateExpression = "SET actor_user_id = :pseudonym",
                    ConditionExpression = "actor_user_id = :actor",
                    ExpressionAttributeValues = new Dictionary<string, AttributeValue>
                    {
                        [":pseudonym"] = DynamoValues.S(pseudonym),
                        [":actor"] = DynamoValues.S(userId)
                    }
                }, cancellationToken);
                rewritten++;
            }
            lastKey = scan.LastEvaluatedKey is { Count: > 0 } ? scan.LastEvaluatedKey : null;
        }
        while (lastKey is not null);
        return rewritten;
    }
}
