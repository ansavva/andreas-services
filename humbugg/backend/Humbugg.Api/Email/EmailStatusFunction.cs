using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using Amazon.Lambda.RuntimeSupport;
using Amazon.Lambda.Serialization.SystemTextJson;
using Amazon.Lambda.SQSEvents;
using System.Globalization;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Humbugg.Api.Email;

internal static class EmailStatusRuntime
{
    public static async Task RunAsync()
    {
        var settings = HumbuggSettings.FromEnvironment();
        using var db = new AmazonDynamoDBClient(
            Amazon.RegionEndpoint.GetBySystemName(settings.AwsRegion));
        using var loggerFactory = LoggerFactory.Create(logging => logging.AddJsonConsole());
        var handler = new EmailStatusHandler(
            db,
            settings.EmailMessagesTable,
            loggerFactory.CreateLogger<EmailStatusHandler>());
        using var bootstrap = LambdaBootstrapBuilder
            .Create<SQSEvent, SQSBatchResponse>(
                handler.HandleAsync,
                new DefaultLambdaJsonSerializer())
            .Build();
        await bootstrap.RunAsync();
    }
}

internal sealed class EmailStatusHandler(
    IAmazonDynamoDB db,
    string tableName,
    ILogger<EmailStatusHandler> logger)
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private static readonly IReadOnlyDictionary<string, int> StatusRanks =
        new Dictionary<string, int>(StringComparer.Ordinal)
        {
            ["accepted"] = 10,
            ["delivery_delay"] = 20,
            ["delivery"] = 30,
            ["reject"] = 40,
            ["bounce"] = 40,
            ["suppressed"] = 40,
            ["disabled"] = 40,
            ["attachment_blocked"] = 40,
            ["complaint"] = 50
        };

    public async Task<SQSBatchResponse> HandleAsync(SQSEvent sqsEvent)
    {
        var failures = new List<SQSBatchResponse.BatchItemFailure>();
        foreach (var record in sqsEvent.Records)
        {
            try
            {
                var statusEvent = JsonSerializer.Deserialize<MailerStatusEvent>(
                    record.Body,
                    JsonOptions) ?? throw new InvalidOperationException("Status event body is empty.");
                await ApplyAsync(statusEvent, CancellationToken.None);
            }
            catch (Exception exception)
            {
                logger.LogError(
                    exception,
                    "Mailer status event {SqsMessageId} could not be processed",
                    record.MessageId);
                failures.Add(new SQSBatchResponse.BatchItemFailure
                {
                    ItemIdentifier = record.MessageId
                });
            }
        }
        return new SQSBatchResponse(failures);
    }

    internal async Task ApplyAsync(
        MailerStatusEvent statusEvent,
        CancellationToken cancellationToken)
    {
        Validate(statusEvent);
        var rank = StatusRanks[statusEvent.Status];
        var occurredAt = statusEvent.OccurredAt.UtcDateTime.ToString(
            "O",
            CultureInfo.InvariantCulture);
        var values = new Dictionary<string, AttributeValue>
        {
            [":status"] = new() { S = statusEvent.Status },
            [":rank"] = new() { N = rank.ToString(CultureInfo.InvariantCulture) },
            [":occurred_at"] = new() { S = occurredAt },
            [":event_id"] = new() { S = statusEvent.EventId },
            [":service_id"] = new() { S = statusEvent.ServiceId },
            [":category"] = new() { S = statusEvent.Category },
            [":message_class"] = new() { S = statusEvent.MessageClass },
            [":expires_at"] = new()
            {
                N = statusEvent.OccurredAt
                    .AddDays(90)
                    .ToUnixTimeSeconds()
                    .ToString(CultureInfo.InvariantCulture)
            }
        };
        var update = """
            SET #status = :status,
                status_rank = :rank,
                status_occurred_at = :occurred_at,
                last_event_id = :event_id,
                service_id = :service_id,
                category = :category,
                message_class = :message_class,
                expires_at = :expires_at
            """;
        if (!string.IsNullOrWhiteSpace(statusEvent.ProviderMessageId))
        {
            update += ", provider_message_id = :provider_message_id";
            values[":provider_message_id"] = new AttributeValue
            {
                S = statusEvent.ProviderMessageId
            };
        }

        try
        {
            await db.UpdateItemAsync(new UpdateItemRequest
            {
                TableName = tableName,
                Key = new()
                {
                    ["message_id"] = new AttributeValue
                    {
                        S = statusEvent.ApplicationMessageId
                    }
                },
                UpdateExpression = update,
                ConditionExpression = """
                    attribute_not_exists(last_event_id)
                    OR (
                        last_event_id <> :event_id
                        AND (
                            attribute_not_exists(status_rank)
                            OR status_rank < :rank
                            OR (
                                status_rank = :rank
                                AND #status = :status
                                AND status_occurred_at < :occurred_at
                            )
                        )
                    )
                    """,
                ExpressionAttributeNames = new()
                {
                    ["#status"] = "status"
                },
                ExpressionAttributeValues = values
            }, cancellationToken);
        }
        catch (ConditionalCheckFailedException)
        {
            logger.LogInformation(
                "Ignored duplicate or stale Mailer status event {EventId} for {MessageId}",
                statusEvent.EventId,
                statusEvent.ApplicationMessageId);
        }
    }

    private static void Validate(MailerStatusEvent statusEvent)
    {
        if (statusEvent.SchemaVersion != 1)
            throw new InvalidOperationException("Unsupported Mailer status schema version.");
        if (!statusEvent.ServiceId.Equals("humbugg", StringComparison.Ordinal))
            throw new InvalidOperationException("Status event belongs to another service.");
        if (string.IsNullOrWhiteSpace(statusEvent.EventId) ||
            string.IsNullOrWhiteSpace(statusEvent.ApplicationMessageId) ||
            string.IsNullOrWhiteSpace(statusEvent.Category) ||
            string.IsNullOrWhiteSpace(statusEvent.MessageClass))
            throw new InvalidOperationException("Status event is missing required identifiers.");
        if (!StatusRanks.ContainsKey(statusEvent.Status))
            throw new InvalidOperationException("Status event contains an unsupported status.");
    }
}

internal sealed record MailerStatusEvent(
    [property: JsonPropertyName("schema_version")] int SchemaVersion,
    [property: JsonPropertyName("event_id")] string EventId,
    [property: JsonPropertyName("service_id")] string ServiceId,
    [property: JsonPropertyName("application_message_id")] string ApplicationMessageId,
    [property: JsonPropertyName("category")] string Category,
    [property: JsonPropertyName("message_class")] string MessageClass,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("occurred_at")] DateTimeOffset OccurredAt,
    [property: JsonPropertyName("provider_message_id")] string? ProviderMessageId,
    [property: JsonPropertyName("reason")] string? Reason);
