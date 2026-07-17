using Amazon.DynamoDBv2;
using Amazon.Lambda.RuntimeSupport;
using Amazon.Lambda.Serialization.SystemTextJson;
using Amazon.Lambda.SQSEvents;
using Humbugg.Api.Services.Email.StatusProcessing;
using System.Text.Json;

namespace Humbugg.Api.Consumers.EmailStatus;

/// <summary>
/// Hosts the AWS Lambda SQS adapter for Mailer delivery-status events.
/// Business rules remain in <see cref="EmailStatusHandler"/>.
/// </summary>
internal sealed class AwsLambdaEmailStatusConsumer(
    EmailStatusHandler handler,
    ILogger<AwsLambdaEmailStatusConsumer> logger)
{
    /// <summary>
    /// Gets the value used to select this consumer through <c>HUMBUGG_CONSUMER</c>.
    /// </summary>
    public const string ConsumerName = "email-status";

    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    /// <summary>
    /// Processes an SQS batch and reports only failed records so Lambda can retry
    /// individual messages without replaying the successful records.
    /// </summary>
    public async Task<SQSBatchResponse> ConsumeAsync(SQSEvent sqsEvent)
    {
        var failures = new List<SQSBatchResponse.BatchItemFailure>();
        foreach (var record in sqsEvent.Records)
        {
            try
            {
                var statusEvent = JsonSerializer.Deserialize<MailerStatusEvent>(
                    record.Body,
                    JsonOptions) ?? throw new InvalidOperationException("Status event body is empty.");
                await handler.ApplyAsync(statusEvent, CancellationToken.None);
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

    /// <summary>
    /// Builds the consumer's AWS dependencies and starts the Lambda runtime loop.
    /// </summary>
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
        var consumer = new AwsLambdaEmailStatusConsumer(
            handler,
            loggerFactory.CreateLogger<AwsLambdaEmailStatusConsumer>());
        using var bootstrap = LambdaBootstrapBuilder
            .Create<SQSEvent, SQSBatchResponse>(
                consumer.ConsumeAsync,
                new DefaultLambdaJsonSerializer())
            .Build();
        await bootstrap.RunAsync();
    }
}
