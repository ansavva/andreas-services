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
        // **Not `HumbuggSettings.FromEnvironment()`.** That is the API's contract, and
        // since #239 it *requires* all eight DynamoDB table variables and throws naming
        // the first one missing. This consumer is deployed with two variables and uses
        // two fields, so calling it made the Lambda throw at init on every invocation:
        // the feedback queue was never drained, no delivery status was ever written, and
        // the smoke test polled a status that stayed `None` for six days.
        //
        // A consumer asks for what it reads. Widening the deploy to set seven tables this
        // code never touches would have restored the Lambda and left the next table added
        // to the API free to break it again.
        var region = ResolveRegion();
        var messagesTable = RequiredTable("HUMBUGG_EMAIL_MESSAGES_TABLE");
        using var db = new AmazonDynamoDBClient(Amazon.RegionEndpoint.GetBySystemName(region));
        using var loggerFactory = LoggerFactory.Create(logging => logging.AddJsonConsole());
        var handler = new EmailStatusHandler(
            db,
            messagesTable,
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

    /// <summary>
    /// The region this consumer's DynamoDB client targets, resolved exactly as
    /// <c>HumbuggSettings</c> resolves it so the two cannot disagree.
    /// </summary>
    private static string ResolveRegion() =>
        Environment.GetEnvironmentVariable("AWS_REGION")
        ?? Environment.GetEnvironmentVariable("AWS_DEFAULT_REGION")
        ?? "us-east-1";

    /// <summary>
    /// Reads a required table name, or throws naming the variable.
    /// </summary>
    /// <remarks>
    /// Deliberately the same discipline as the API's: table names are per-environment
    /// and have no safe default, so a missing one fails loudly rather than silently
    /// targeting a table that does not exist.
    /// </remarks>
    /// <exception cref="InvalidOperationException">Thrown when the variable is unset or blank.</exception>
    internal static string RequiredTable(string variable) =>
        Environment.GetEnvironmentVariable(variable) is { } value && !string.IsNullOrWhiteSpace(value)
            ? value.Trim()
            : throw new InvalidOperationException(
                $"{variable} is not set. DynamoDB table names are per-environment and have no default. " +
                "In CI the deploy workflow sets it on the email-status Lambda.");
}
