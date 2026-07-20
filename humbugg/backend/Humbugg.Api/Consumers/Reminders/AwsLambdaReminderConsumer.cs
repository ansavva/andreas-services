using Amazon.DynamoDBv2;
using Amazon.Lambda.RuntimeSupport;
using Amazon.Lambda.Serialization.SystemTextJson;
using Amazon.Runtime.Credentials;
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
        var settings = HumbuggSettings.FromEnvironment();
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

    private sealed class BackgroundUser : ICurrentUser
    {
        public string UserId => "system:reminders";
    }

    private sealed class BackgroundCorrelation : IRequestCorrelation
    {
        public string CorrelationId => $"scheduled:{DateTimeOffset.UtcNow:yyyyMMddHHmm}";
    }
}
