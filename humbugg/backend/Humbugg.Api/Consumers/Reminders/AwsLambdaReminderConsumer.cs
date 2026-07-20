using Amazon.DynamoDBv2;
using Amazon.Lambda.RuntimeSupport;
using Amazon.Lambda.Serialization.SystemTextJson;
using Amazon.Runtime.Credentials;
using Humbugg.Api.Consumers.EmailStatus;
using Humbugg.Api.Data;
using Humbugg.Api.Services;
using Humbugg.Api.Services.Email.Adapters.Aws;
using Humbugg.Api.Services.Email.Adapters.Http;
using Humbugg.Api.Services.Email.Core;
using System.Text.Json;

namespace Humbugg.Api.Consumers.Reminders;

internal sealed class AwsLambdaReminderConsumer(IReminderProcessor processor)
{
    public const string ConsumerName = "reminders";

    public async Task<string> ConsumeAsync(JsonElement _)
    {
        await processor.ProcessDueAsync(DateTimeOffset.UtcNow, CancellationToken.None);
        return "ok";
    }

    public static async Task RunAsync()
    {
        var settings = SettingsFromEnvironment();
        using var db = new AmazonDynamoDBClient(
            Amazon.RegionEndpoint.GetBySystemName(settings.AwsRegion));
        using var loggerFactory = LoggerFactory.Create(logging => logging.AddJsonConsole());
        using var http = new HttpClient
        {
            BaseAddress = new Uri(settings.MailerBaseUrl, UriKind.Absolute),
            Timeout = TimeSpan.FromSeconds(15)
        };
        var signer = new AwsSigV4MailerRequestSigner(
            DefaultAWSCredentialsIdentityResolver.GetCredentials(
                new AmazonDynamoDBConfig
                {
                    RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(settings.AwsRegion)
                }),
            settings.AwsRegion);
        var profiles = new ProfileRepository(db, settings);
        var email = new TransactionalEmailService(
            new MailerEmailTransport(new MailerClient(http, settings, signer)),
            new DynamoDbEmailDeliveryLedger(db, settings),
            new AccountEmailPreferenceGate(
                profiles,
                loggerFactory.CreateLogger<AccountEmailPreferenceGate>()),
            loggerFactory.CreateLogger<TransactionalEmailService>());
        var audit = new AuditTrail(
            new BackgroundUser(),
            new BackgroundCorrelation(),
            new AuditRepository(db, settings));
        var processor = new ReminderService(
            new BackgroundUser(),
            new GroupRepository(db, settings),
            new MembershipRepository(db, settings),
            new InvitationRepository(db, settings),
            new ReminderRepository(db, settings),
            PlanCatalog.FromEnvironment(),
            new TransactionalEmailTemplates(),
            email,
            audit,
            settings);
        var consumer = new AwsLambdaReminderConsumer(processor);
        using var bootstrap = LambdaBootstrapBuilder
            .Create<JsonElement, string>(
                consumer.ConsumeAsync,
                new DefaultLambdaJsonSerializer())
            .Build();
        await bootstrap.RunAsync();
    }

    // A table this consumer never opens. Not a plausible DynamoDB name — the colon
    // is not a legal character — so if a repository is ever added here that does read
    // one of these, the call fails immediately and the error names its own cause,
    // rather than resolving against some real table by accident.
    private const string UnusedTable = "unused:reminders-consumer";

    // **Not `HumbuggSettings.FromEnvironment()`.** That is the API's contract: it
    // requires every table the API reads, and this Lambda reads seven of them. Calling
    // it here couples the scheduled consumer to tables it never opens, so adding one to
    // the API later breaks reminders at cold start with an error about a table this code
    // does not use. That is #387 exactly — the email-status consumer called
    // FromEnvironment(), the deploy sent it two variables, and humbugg's prod deploy went
    // red for six days. Require the seven this consumer actually reads and nothing more.
    internal static HumbuggSettings SettingsFromEnvironment()
    {
        var appBaseUrl = (Environment.GetEnvironmentVariable("APP_BASE_URL")
            ?? "http://localhost:5173").TrimEnd('/');
        var required = AwsLambdaEmailStatusConsumer.RequiredTable;

        return new HumbuggSettings(
            AwsRegion: Environment.GetEnvironmentVariable("AWS_REGION")
                ?? Environment.GetEnvironmentVariable("AWS_DEFAULT_REGION")
                ?? "us-east-1",
            CognitoRegion: "us-east-1",
            CognitoUserPoolId: "unused",
            CognitoClientId: "unused",
            CorsOrigins: [],
            AppBaseUrl: appBaseUrl,
            DynamoDbEndpointUrl: Environment.GetEnvironmentVariable("DYNAMODB_ENDPOINT_URL"),
            ProfilesTable: required("HUMBUGG_PROFILES_TABLE"),
            GroupsTable: required("HUMBUGG_GROUPS_TABLE"),
            GroupMembersTable: required("HUMBUGG_GROUPMEMBERS_TABLE"),
            DrawsTable: UnusedTable,
            AuditEventsTable: required("HUMBUGG_AUDIT_EVENTS_TABLE"),
            AnalyticsEventsTable: UnusedTable,
            EmailProvider: Environment.GetEnvironmentVariable("HUMBUGG_EMAIL_PROVIDER") ?? "capture",
            EmailMessagesTable: required("HUMBUGG_EMAIL_MESSAGES_TABLE"),
            MailerBaseUrl: (Environment.GetEnvironmentVariable("HUMBUGG_MAILER_BASE_URL")
                ?? "http://host.docker.internal:8026").TrimEnd('/'),
            MailerAuthMode: Environment.GetEnvironmentVariable("HUMBUGG_MAILER_AUTH_MODE") ?? "none",
            MailerServiceId: Environment.GetEnvironmentVariable("HUMBUGG_MAILER_SERVICE_ID") ?? "humbugg",
            AvatarBaseUrl: appBaseUrl,
            BillingRecordsTable: UnusedTable,
            InvitationsTable: required("HUMBUGG_INVITATIONS_TABLE"),
            RemindersTable: required("HUMBUGG_REMINDERS_TABLE"));
    }

    private sealed class BackgroundUser : ICurrentUser
    {
        public string UserId => "system:reminders";
    }

    private sealed class BackgroundCorrelation : IRequestCorrelation
    {
        public string CorrelationId => $"scheduled:{DateTimeOffset.UtcNow:yyyyMMddHHmm}";
    }
}
