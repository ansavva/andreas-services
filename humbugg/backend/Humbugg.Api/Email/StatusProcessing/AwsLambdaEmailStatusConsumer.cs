using Amazon.DynamoDBv2;
using Amazon.Lambda.RuntimeSupport;
using Amazon.Lambda.Serialization.SystemTextJson;
using Amazon.Lambda.SQSEvents;
using System.Text.Json;

namespace Humbugg.Api.Email.StatusProcessing;

internal sealed class AwsLambdaEmailStatusConsumer(
    EmailStatusHandler handler,
    ILogger<AwsLambdaEmailStatusConsumer> logger)
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

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
