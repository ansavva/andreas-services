using Amazon.DynamoDBv2;
using Amazon.Lambda.RuntimeSupport;
using Amazon.Lambda.Serialization.SystemTextJson;
using Amazon.Lambda.SQSEvents;
using Amazon.SQS;
using Amazon.SQS.Model;
using Humbugg.Api.Consumers.EmailStatus;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Humbugg.Api.Consumers.StripeWebhooks;

/// <summary>
/// Drains the webhook relay's queue: the process half of the Stripe webhook path, in every
/// environment.
/// </summary>
/// <remarks>
/// <para>
/// Stripe posts to a public API Gateway (<c>infra/modules/webhook_relay</c>); a dependency-free
/// receiver puts the raw body and its <c>Stripe-Signature</c> on an SQS queue; this drains the queue
/// and hands each event to <see cref="IBillingService.ProcessQueuedWebhookAsync"/> — the same
/// verification and the same <c>ApplyEventAsync</c> the HTTP route runs. Studio's
/// <c>modules/callbacks</c> is the shape: receive in a zip nobody builds, process in the service's
/// own image.
/// </para>
/// <para>
/// <b>One consumer, two hosts.</b> In production this is a Lambda on an event-source mapping, the
/// API's container image entered through <c>ConsumerHost</c> like the email-status and reminder
/// consumers. On a developer's machine it is the same image as a second Compose service,
/// long-polling this machine's own queue — <see cref="RunAsync"/> picks by whether the Lambda
/// runtime is present. That is the whole reason the receive and process halves are separate: Stripe
/// cannot reach <c>localhost:5001</c>, so before the relay the code that closes a purchase in
/// production was reachable locally only through the Stripe CLI's live relay, which lost every
/// event emitted while it was not running.
/// </para>
/// <para>
/// <b>Routing.</b> Every dev machine registers its own endpoint in one shared Stripe sandbox, and
/// Stripe fans every event out to every endpoint in the account — so a dev queue receives other
/// machines' purchases too. The backend stamps <c>HUMBUGG_ENVIRONMENT</c> into every Checkout's
/// metadata; an event carrying somebody else's is dropped here with a log line rather than handed
/// to <c>ParseWebhook</c>, which would refuse it for the same reason. An event with no environment
/// is passed through — the gateway is the authority on what it accepts. In prod every event carries
/// <c>production</c> and the check costs nothing.
/// </para>
/// <para>
/// <b>What a refusal means.</b> A 409 from the billing repository is "not yet": Stripe emits
/// <c>charge.succeeded</c> and <c>checkout.session.completed</c> within the same second in no fixed
/// order, and a charge whose session has not been seen is refused until it has. That record is
/// reported failed so SQS returns it after the visibility timeout — the queue doing what Stripe's
/// own retry schedule would. Any other <see cref="ApiException"/> is a body the service will never
/// accept (bad signature, wrong metadata, unknown purchase); a retry delivers the identical body, so
/// it is logged and consumed. Anything else — a DynamoDB outage — is a failure and comes back.
/// </para>
/// </remarks>
internal sealed class AwsLambdaStripeWebhookConsumer(
    IBillingService billing,
    string environment,
    ILogger<AwsLambdaStripeWebhookConsumer> logger)
{
    /// <summary>Gets the value used to select this consumer through <c>HUMBUGG_CONSUMER</c>.</summary>
    public const string ConsumerName = "stripe-webhooks";

    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    /// <summary>
    /// The receiver's envelope. Base64 because the signature is over the exact bytes Stripe sent
    /// and a JSON round trip of the decoded string is not guaranteed to reproduce them.
    /// </summary>
    internal sealed record Envelope(
        [property: JsonPropertyName("signature")] string? Signature,
        [property: JsonPropertyName("body_b64")] string? BodyB64,
        [property: JsonPropertyName("received_at")] string? ReceivedAt);

    /// <summary>
    /// Processes an SQS batch and reports only the records to retry, so Lambda returns those to the
    /// queue without replaying the ones that succeeded.
    /// </summary>
    public async Task<SQSBatchResponse> ConsumeAsync(SQSEvent sqsEvent)
    {
        var failures = new List<SQSBatchResponse.BatchItemFailure>();
        foreach (var record in sqsEvent.Records)
        {
            if (await ConsumeOneAsync(record.Body, record.MessageId) == Outcome.Retry)
                failures.Add(new SQSBatchResponse.BatchItemFailure { ItemIdentifier = record.MessageId });
        }
        return new SQSBatchResponse(failures);
    }

    internal enum Outcome { Done, Retry }

    internal async Task<Outcome> ConsumeOneAsync(string messageBody, string messageId)
    {
        Envelope? envelope;
        try { envelope = JsonSerializer.Deserialize<Envelope>(messageBody, JsonOptions); }
        catch (JsonException) { envelope = null; }
        if (envelope?.Signature is null || envelope.BodyB64 is null)
        {
            logger.LogWarning("Message {SqsMessageId} is not the receiver's envelope; dropping it", messageId);
            return Outcome.Done;
        }

        string payload;
        try { payload = System.Text.Encoding.UTF8.GetString(Convert.FromBase64String(envelope.BodyB64)); }
        catch (FormatException)
        {
            logger.LogWarning("Message {SqsMessageId} carries a body that is not base64; dropping it", messageId);
            return Outcome.Done;
        }

        var (label, target) = Describe(payload);
        if (target is not null && !string.Equals(target, environment, StringComparison.Ordinal))
        {
            logger.LogInformation("Skipping {Event}: for {Target}, this is {Environment}", label, target, environment);
            return Outcome.Done;
        }

        try
        {
            await billing.ProcessQueuedWebhookAsync(payload, envelope.Signature, CancellationToken.None);
            logger.LogInformation("Applied {Event}", label);
            return Outcome.Done;
        }
        catch (ApiException exception) when (exception.StatusCode == 409)
        {
            logger.LogInformation("{Event} is not applicable yet ({Reason}); will retry", label, exception.Message);
            return Outcome.Retry;
        }
        catch (ApiException exception)
        {
            logger.LogWarning("{Event} refused with {Status} ({Reason}); not retrying", label, exception.StatusCode, exception.Message);
            return Outcome.Done;
        }
        catch (Exception exception)
        {
            logger.LogError(exception, "{Event} could not be applied; will retry", label);
            return Outcome.Retry;
        }
    }

    /// <summary>
    /// A log label and the event's target environment, read off the unverified body. Read-only and
    /// for routing and logging alone: nothing here is acted on before the signature is checked.
    /// </summary>
    private static (string Label, string? Target) Describe(string payload)
    {
        try
        {
            using var document = JsonDocument.Parse(payload);
            var root = document.RootElement;
            var type = root.TryGetProperty("type", out var t) ? t.GetString() : null;
            var id = root.TryGetProperty("id", out var i) ? i.GetString() : null;
            string? target = null;
            if (root.TryGetProperty("data", out var data) &&
                data.TryGetProperty("object", out var obj) &&
                obj.TryGetProperty("metadata", out var metadata) &&
                metadata.ValueKind == JsonValueKind.Object &&
                metadata.TryGetProperty("environment", out var env))
                target = env.GetString();
            return ($"{type ?? "event"} {id}".Trim(), string.IsNullOrWhiteSpace(target) ? null : target);
        }
        catch (JsonException)
        {
            return ("unparseable event", null);
        }
    }

    // ── Hosting ──────────────────────────────────────────────────────────────────

    /// <summary>
    /// Builds the consumer and runs it as a Lambda when the Lambda runtime is present, or as a
    /// long-polling process against <c>HUMBUGG_WEBHOOK_QUEUE_URL</c> when it is not.
    /// </summary>
    public static async Task RunAsync()
    {
        using var loggerFactory = LoggerFactory.Create(logging => logging.AddJsonConsole());
        var logger = loggerFactory.CreateLogger<AwsLambdaStripeWebhookConsumer>();

        // A consumer asks for what it reads — the email-status consumer's lesson (#239). The two
        // tables ApplyEventAsync writes, the Stripe settings ParseWebhook verifies with, and the
        // environment the Checkout metadata is compared against.
        var stripeSettings = StripeSettings.FromEnvironment();
        var settings = SettingsFromEnvironment();
        var region = Amazon.RegionEndpoint.GetBySystemName(settings.AwsRegion);
        using var db = string.IsNullOrWhiteSpace(settings.DynamoDbEndpointUrl)
            ? new AmazonDynamoDBClient(region)
            : new AmazonDynamoDBClient(new AmazonDynamoDBConfig { ServiceURL = settings.DynamoDbEndpointUrl });
        var billing = new BillingService(
            new BackgroundUser(),
            new GroupRepository(db, settings),
            new BillingRepository(db, settings),
            PlanCatalog.FromEnvironment(),
            new StripeGateway(stripeSettings),
            stripeSettings);
        var consumer = new AwsLambdaStripeWebhookConsumer(billing, stripeSettings.Environment, logger);

        if (!string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("AWS_LAMBDA_RUNTIME_API")))
        {
            using var bootstrap = LambdaBootstrapBuilder
                .Create<SQSEvent, SQSBatchResponse>(consumer.ConsumeAsync, new DefaultLambdaJsonSerializer())
                .Build();
            await bootstrap.RunAsync();
            return;
        }

        await consumer.PollAsync(region, logger, stripeSettings);
    }

    /// <summary>
    /// The developer's host: one held connection to this machine's queue, twenty seconds at a
    /// time (the SQS maximum), because the queue is empty almost all of the time.
    /// </summary>
    /// <remarks>
    /// With Stripe disabled there is nothing to relay, and a Compose service that exits makes a
    /// noise the developer has to learn to ignore — so this says so once and idles. Its failures
    /// are its own: a ReceiveMessage error is logged and retried, never fatal.
    /// </remarks>
    private async Task PollAsync(Amazon.RegionEndpoint region, ILogger log, StripeSettings stripeSettings)
    {
        var queueUrl = Environment.GetEnvironmentVariable("HUMBUGG_WEBHOOK_QUEUE_URL");
        if (!stripeSettings.IsEnabled || string.IsNullOrWhiteSpace(queueUrl))
        {
            log.LogInformation(
                "Stripe is {Mode} and HUMBUGG_WEBHOOK_QUEUE_URL is {Queue}; nothing to relay. Idling. Set HUMBUGG_STRIPE_MODE=test and re-run dev-aws-setup.sh to register this machine's endpoint",
                stripeSettings.IsEnabled ? "enabled" : "disabled",
                string.IsNullOrWhiteSpace(queueUrl) ? "unset" : "set");
            await Task.Delay(Timeout.InfiniteTimeSpan);
            return;
        }

        using var sqs = new AmazonSQSClient(region);
        log.LogInformation("Draining {Queue} as {Environment}", queueUrl[(queueUrl.LastIndexOf('/') + 1)..], environment);
        while (true)
        {
            ReceiveMessageResponse received;
            try
            {
                received = await sqs.ReceiveMessageAsync(new ReceiveMessageRequest
                {
                    QueueUrl = queueUrl,
                    MaxNumberOfMessages = 10,
                    WaitTimeSeconds = 20,
                });
            }
            catch (Exception exception)
            {
                log.LogWarning(exception, "ReceiveMessage failed; retrying in ten seconds");
                await Task.Delay(TimeSpan.FromSeconds(10));
                continue;
            }
            foreach (var message in received.Messages ?? [])
            {
                if (await ConsumeOneAsync(message.Body, message.MessageId) == Outcome.Done)
                    await sqs.DeleteMessageAsync(queueUrl, message.ReceiptHandle);
            }
        }
    }

    /// <summary>
    /// Exactly the two tables the billing repository writes. The rest are named so a mistaken
    /// read fails on a table that does not exist rather than on a real one.
    /// </summary>
    internal static HumbuggSettings SettingsFromEnvironment()
    {
        const string unused = "unused:stripe-webhooks-consumer";
        var required = AwsLambdaEmailStatusConsumer.RequiredTable;
        return new HumbuggSettings(
            AwsRegion: Environment.GetEnvironmentVariable("AWS_REGION")
                ?? Environment.GetEnvironmentVariable("AWS_DEFAULT_REGION")
                ?? "us-east-1",
            CognitoRegion: "us-east-1",
            CognitoUserPoolId: "unused",
            CognitoClientId: "unused",
            CorsOrigins: [],
            AppBaseUrl: "http://localhost:8081",
            DynamoDbEndpointUrl: Environment.GetEnvironmentVariable("DYNAMODB_ENDPOINT_URL"),
            ProfilesTable: unused,
            GroupsTable: required("HUMBUGG_GROUPS_TABLE"),
            GroupMembersTable: unused,
            DrawsTable: unused,
            AuditEventsTable: unused,
            AnalyticsEventsTable: unused,
            BillingRecordsTable: required("HUMBUGG_BILLING_TABLE"));
    }

    private sealed class BackgroundUser : ICurrentUser
    {
        public string UserId => "system:stripe-webhooks";
    }
}
