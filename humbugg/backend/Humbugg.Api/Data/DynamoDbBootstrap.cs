using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;

namespace Humbugg.Api.Data;

internal sealed class DynamoDbBootstrap(IAmazonDynamoDB db, HumbuggSettings settings, ILogger<DynamoDbBootstrap> logger) : IHostedService
{
    public async Task StartAsync(CancellationToken cancellationToken)
    {
        await EnsureAsync(settings.ProfilesTable, "user_id", cancellationToken);
        await EnsureAsync(settings.GroupsTable, "group_id", cancellationToken);
        await EnsureMembersAsync(cancellationToken);
        await EnsureAsync(settings.DrawsTable, "group_id", cancellationToken);
        await EnsureAsync(settings.AuditEventsTable, "group_id", cancellationToken, "event_id");
        await EnsureAsync(settings.AnalyticsEventsTable, "idempotency_key", cancellationToken);
        await EnsureAsync(settings.EmailMessagesTable, "message_id", cancellationToken);
        await EnsureBillingAsync(cancellationToken);
    }

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;

    private async Task EnsureAsync(string table, string hashKey, CancellationToken cancellationToken, string? rangeKey = null)
    {
        if (await ExistsAsync(table, cancellationToken)) return;
        var request = new CreateTableRequest
        {
            TableName = table,
            BillingMode = BillingMode.PAY_PER_REQUEST,
            AttributeDefinitions = [new(hashKey, ScalarAttributeType.S)],
            KeySchema = [new(hashKey, KeyType.HASH)]
        };
        if (rangeKey is not null)
        {
            request.AttributeDefinitions.Add(new(rangeKey, ScalarAttributeType.S));
            request.KeySchema.Add(new(rangeKey, KeyType.RANGE));
        }
        await db.CreateTableAsync(request, cancellationToken);
        logger.LogInformation("Created local DynamoDB table {Table}", table);
    }

    private async Task EnsureMembersAsync(CancellationToken cancellationToken)
    {
        if (await ExistsAsync(settings.GroupMembersTable, cancellationToken)) return;
        await db.CreateTableAsync(new CreateTableRequest
        {
            TableName = settings.GroupMembersTable,
            BillingMode = BillingMode.PAY_PER_REQUEST,
            AttributeDefinitions = [new("member_id", ScalarAttributeType.S), new("user_id", ScalarAttributeType.S), new("group_id", ScalarAttributeType.S)],
            KeySchema = [new("member_id", KeyType.HASH)],
            GlobalSecondaryIndexes =
            [
                new() { IndexName = "user_id-index", KeySchema = [new("user_id", KeyType.HASH)], Projection = new Projection { ProjectionType = ProjectionType.ALL } },
                new() { IndexName = "group_id-index", KeySchema = [new("group_id", KeyType.HASH)], Projection = new Projection { ProjectionType = ProjectionType.ALL } }
            ]
        }, cancellationToken);
        logger.LogInformation("Created local DynamoDB table {Table}", settings.GroupMembersTable);
    }

    private async Task EnsureBillingAsync(CancellationToken cancellationToken)
    {
        if (await ExistsAsync(settings.BillingRecordsTable, cancellationToken)) return;
        await db.CreateTableAsync(new CreateTableRequest
        {
            TableName = settings.BillingRecordsTable,
            BillingMode = BillingMode.PAY_PER_REQUEST,
            AttributeDefinitions =
            [
                new("record_id", ScalarAttributeType.S),
                new("group_id", ScalarAttributeType.S),
            ],
            KeySchema = [new("record_id", KeyType.HASH)],
            GlobalSecondaryIndexes =
            [
                new()
                {
                    IndexName = "group_id-index",
                    KeySchema = [new("group_id", KeyType.HASH)],
                    Projection = new Projection { ProjectionType = ProjectionType.ALL },
                },
            ],
        }, cancellationToken);
        logger.LogInformation("Created local DynamoDB table {Table}", settings.BillingRecordsTable);
    }

    private async Task<bool> ExistsAsync(string table, CancellationToken cancellationToken)
    {
        try { await db.DescribeTableAsync(table, cancellationToken); return true; }
        catch (ResourceNotFoundException) { return false; }
    }
}
