using Amazon.DynamoDBv2;
using Amazon.Lambda.AspNetCoreServer.Hosting;
using Amazon.Runtime.Credentials;
using Humbugg.Api.Consumers;
using Humbugg.Api.Data;
using Humbugg.Api.Middleware;
using Humbugg.Api.Services;
using Humbugg.Api.Services.Email.Adapters.Aws;
using Humbugg.Api.Services.Email.Adapters.Http;
using Humbugg.Api.Services.Email.Adapters.Memory;
using Humbugg.Api.Services.Email.Core;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Mvc;
using Microsoft.IdentityModel.Tokens;
using System.Text.Json;
using System.Text.Json.Serialization;

// ─── Background consumer hosting ────────────────────────────────────────────
// Consumer Lambdas use this executable but do not start the ASP.NET Core API.
// ConsumerHost is the single registry for all current and future consumers.
if (ConsumerHost.IsConsumerProcess)
{
    await ConsumerHost.RunConfiguredAsync();
    return;
}

// ─── HTTP API hosting ────────────────────────────────────────────────────────
var builder = WebApplication.CreateBuilder(args);
var settings = HumbuggSettings.FromEnvironment();
builder.Services.AddSingleton(settings);
builder.Services.AddSingleton<IPlanCatalog>(PlanCatalog.FromEnvironment());
builder.Services.AddSingleton(AnalyticsOptions.FromEnvironment());
// Validates Stripe billing configuration at startup: fails fast on missing test-mode
// credentials and refuses any live-mode key/mode (blocked pending issue #159).
builder.Services.AddSingleton(StripeSettings.FromEnvironment());

builder.Services.AddControllers().AddJsonOptions(options =>
{
    options.JsonSerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower;
    options.JsonSerializerOptions.DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull;
    options.JsonSerializerOptions.Converters.Add(new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower));
});
builder.Services.AddProblemDetails();
builder.Services.Configure<ApiBehaviorOptions>(options =>
{
    options.InvalidModelStateResponseFactory = _ => new BadRequestObjectResult(new
    {
        error = new { code = "bad_request", message = "The request body is invalid." }
    });
});
builder.Services.AddHttpContextAccessor();
// The API answers on its own domain (api.humbugg.com), so every browser request is
// cross-origin and CORS is load-bearing rather than decorative. ASP.NET is the single
// source of the Access-Control-* headers — API Gateway deliberately emits none of its
// own, because a browser rejects a response carrying two Allow-Origin headers.
builder.Services.AddCors(options => options.AddDefaultPolicy(policy =>
    policy.WithOrigins(settings.CorsOrigins).AllowAnyHeader().AllowAnyMethod()));

builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme).AddJwtBearer(options =>
{
    options.Authority = $"https://cognito-idp.{settings.CognitoRegion}.amazonaws.com/{settings.CognitoUserPoolId}";
    options.RequireHttpsMetadata = true;
    options.MapInboundClaims = false;
    options.TokenValidationParameters = new TokenValidationParameters
    {
        ValidateIssuer = true,
        ValidateAudience = false,
        ValidateLifetime = true,
        NameClaimType = "sub"
    };
    options.Events = new JwtBearerEvents
    {
        OnTokenValidated = context =>
        {
            var tokenUse = context.Principal?.FindFirst("token_use")?.Value;
            var clientId = context.Principal?.FindFirst("client_id")?.Value;
            if (tokenUse != "access" || clientId != settings.CognitoClientId)
                context.Fail("The token is not a valid Humbugg access token.");
            return Task.CompletedTask;
        },
        OnChallenge = async context =>
        {
            context.HandleResponse();
            context.Response.StatusCode = StatusCodes.Status401Unauthorized;
            await context.Response.WriteAsJsonAsync(new { error = new { code = "unauthorized", message = "A valid Cognito access token is required." } });
        },
        OnForbidden = context =>
        {
            context.Response.StatusCode = StatusCodes.Status403Forbidden;
            return context.Response.WriteAsJsonAsync(new { error = new { code = "forbidden", message = "You do not have permission to perform this action." } });
        }
    };
});
builder.Services.AddAuthorization();

builder.Services.AddSingleton<IAmazonDynamoDB>(_ =>
{
    var config = new AmazonDynamoDBConfig { RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(settings.AwsRegion) };
    if (!string.IsNullOrWhiteSpace(settings.DynamoDbEndpointUrl))
    {
        config.ServiceURL = settings.DynamoDbEndpointUrl;
        config.UseHttp = settings.DynamoDbEndpointUrl.StartsWith("http://", StringComparison.OrdinalIgnoreCase);
        config.AuthenticationRegion = settings.AwsRegion;
    }
    return new AmazonDynamoDBClient(config);
});
// Avatar object storage. When an application bucket is configured the backend writes to S3 and
// CloudFront serves production objects read-only. With no bucket configured (unit tests), an
// in-process store keeps the upload flow working without any AWS dependency.
if (!string.IsNullOrWhiteSpace(settings.AppBucket))
{
    builder.Services.AddSingleton<Amazon.S3.IAmazonS3>(_ =>
    {
        var s3Config = new Amazon.S3.AmazonS3Config
        {
            RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(settings.AwsRegion)
        };
        if (!string.IsNullOrWhiteSpace(settings.S3EndpointUrl))
        {
            // Optional S3-compatible endpoint support. Path-style addressing is required because
            // virtual-host-style bucket hostnames generally do not resolve for custom endpoints.
            s3Config.ServiceURL = settings.S3EndpointUrl;
            s3Config.ForcePathStyle = true;
            s3Config.UseHttp = settings.S3EndpointUrl.StartsWith("http://", StringComparison.OrdinalIgnoreCase);
            s3Config.AuthenticationRegion = settings.AwsRegion;
        }
        return new Amazon.S3.AmazonS3Client(s3Config);
    });
    builder.Services.AddScoped<IAvatarStore, S3AvatarStore>();
    // Custom S3-compatible endpoints may start empty; ensure the configured bucket exists. This never
    // runs against AWS because AWS-backed development and production buckets are created by Terraform.
    if (!string.IsNullOrWhiteSpace(settings.S3EndpointUrl))
        builder.Services.AddHostedService<S3Bootstrap>();
}
else
{
    builder.Services.AddSingleton<IAvatarStore, InMemoryAvatarStore>();
}
builder.Services.AddSingleton<ITransactionalEmailTemplates, TransactionalEmailTemplates>();
if (settings.EmailProvider.Equals("mailer", StringComparison.OrdinalIgnoreCase))
{
    builder.Services.AddSingleton<IMailerRequestSigner>(_ =>
    {
        if (settings.MailerAuthMode.Equals("none", StringComparison.OrdinalIgnoreCase))
            return new UnsignedMailerRequestSigner();
        if (settings.MailerAuthMode.Equals("sigv4", StringComparison.OrdinalIgnoreCase))
        {
            return new AwsSigV4MailerRequestSigner(
                DefaultAWSCredentialsIdentityResolver.GetCredentials(
                    new AmazonDynamoDBConfig
                    {
                        RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(settings.AwsRegion)
                    }),
                settings.AwsRegion);
        }
        throw new InvalidOperationException(
            $"Unsupported HUMBUGG_MAILER_AUTH_MODE '{settings.MailerAuthMode}'.");
    });
    builder.Services.AddHttpClient<IMailerClient, MailerClient>(client =>
    {
        client.BaseAddress = new Uri(settings.MailerBaseUrl, UriKind.Absolute);
        client.Timeout = TimeSpan.FromSeconds(15);
    });
    builder.Services.AddScoped<IEmailTransport, MailerEmailTransport>();
    builder.Services.AddScoped<IEmailDeliveryLedger, DynamoDbEmailDeliveryLedger>();
}
else if (settings.EmailProvider.Equals("capture", StringComparison.OrdinalIgnoreCase))
{
    builder.Services.AddSingleton<CapturingEmailTransport>();
    builder.Services.AddSingleton<IEmailTransport>(services => services.GetRequiredService<CapturingEmailTransport>());
    builder.Services.AddSingleton<IEmailDeliveryLedger, InMemoryEmailDeliveryLedger>();
}
else
{
    throw new InvalidOperationException($"Unsupported HUMBUGG_EMAIL_PROVIDER '{settings.EmailProvider}'.");
}
// Gates non-essential product email on the recipient's account opt-out; essential mail always sends.
builder.Services.AddScoped<IEmailPreferenceGate, AccountEmailPreferenceGate>();
builder.Services.AddScoped<ITransactionalEmailService, TransactionalEmailService>();
builder.Services.AddScoped<IProfileRepository, ProfileRepository>();
builder.Services.AddScoped<IGroupRepository, GroupRepository>();
builder.Services.AddScoped<IMembershipRepository, MembershipRepository>();
builder.Services.AddScoped<IInvitationRepository, InvitationRepository>();
builder.Services.AddScoped<IAuditRepository, AuditRepository>();
builder.Services.AddScoped<IAuditActorAnonymizer, AuditActorAnonymizer>();
builder.Services.AddScoped<IAnalyticsSink, DynamoDbAnalyticsSink>();
builder.Services.AddScoped<IBillingRepository, BillingRepository>();
builder.Services.AddScoped<ICurrentUser, CurrentUser>();
builder.Services.AddScoped<IRequestCorrelation, HttpRequestCorrelation>();
builder.Services.AddScoped<IAuditTrail, AuditTrail>();
builder.Services.AddScoped<IProductAnalytics, ProductAnalytics>();
builder.Services.AddScoped<IProfileService, ProfileService>();
builder.Services.AddScoped<IGroupService, GroupService>();
builder.Services.AddScoped<IInvitationService, InvitationService>();
builder.Services.AddScoped<IAccountDeletionService, AccountDeletionService>();
builder.Services.AddScoped<IDataExportService, DataExportService>();
builder.Services.AddScoped<IBillingService, BillingService>();
builder.Services.AddSingleton<IStripeGateway, StripeGateway>();
builder.Services.AddSingleton<IMatchingService, MatchingService>();
if (!string.IsNullOrWhiteSpace(settings.DynamoDbEndpointUrl))
    builder.Services.AddHostedService<DynamoDbBootstrap>();
builder.Services.AddAWSLambdaHosting(LambdaEventSource.HttpApi);

var app = builder.Build();
app.UseMiddleware<ApiExceptionMiddleware>();
app.UseCors();
app.UseRouting();
app.UseAuthentication();
app.UseAuthorization();
// Rate limiting is enforced upstream at the API Gateway stage (default route throttling),
// not in-process — see humbugg/infra/modules/compute and humbugg/docs/threat-model.md §4.
app.MapGet("/health", () => Results.Ok(new { status = "ok" }));
app.MapControllers();
app.Run();

public partial class Program;

public sealed record HumbuggSettings(
    string AwsRegion,
    string CognitoRegion,
    string CognitoUserPoolId,
    string CognitoClientId,
    string[] CorsOrigins,
    string AppBaseUrl,
    string? DynamoDbEndpointUrl,
    string ProfilesTable,
    string GroupsTable,
    string GroupMembersTable,
    string DrawsTable,
    string AuditEventsTable,
    string AnalyticsEventsTable,
    string EmailProvider = "capture",
    string EmailMessagesTable = "humbugg-email-messages",
    string MailerBaseUrl = "http://host.docker.internal:8026",
    string MailerAuthMode = "none",
    string MailerServiceId = "humbugg",
    string AppBucket = "",
    string AvatarBaseUrl = "http://localhost:5173",
    string? S3EndpointUrl = null,
    string BillingRecordsTable = "humbugg-billing",
    string InvitationsTable = "humbugg-invitations")
{
    public static HumbuggSettings FromEnvironment()
    {
        var appBaseUrl = (Environment.GetEnvironmentVariable("APP_BASE_URL") ?? "http://localhost:5173").TrimEnd('/');
        return new(
            Environment.GetEnvironmentVariable("AWS_REGION") ?? Environment.GetEnvironmentVariable("AWS_DEFAULT_REGION") ?? "us-east-1",
            Environment.GetEnvironmentVariable("COGNITO_REGION") ?? "us-east-1",
            Environment.GetEnvironmentVariable("COGNITO_USER_POOL_ID") ?? "us-east-1_example",
            Environment.GetEnvironmentVariable("COGNITO_CLIENT_ID") ?? "humbugg-web",
            ParseCorsOrigins(Environment.GetEnvironmentVariable("CORS_ORIGINS")),
            appBaseUrl,
            Environment.GetEnvironmentVariable("DYNAMODB_ENDPOINT_URL"),
            RequiredTable("HUMBUGG_PROFILES_TABLE"),
            RequiredTable("HUMBUGG_GROUPS_TABLE"),
            RequiredTable("HUMBUGG_GROUPMEMBERS_TABLE"),
            RequiredTable("HUMBUGG_DRAWS_TABLE"),
            RequiredTable("HUMBUGG_AUDIT_EVENTS_TABLE"),
            RequiredTable("HUMBUGG_ANALYTICS_EVENTS_TABLE"),
            Environment.GetEnvironmentVariable("HUMBUGG_EMAIL_PROVIDER") ?? "capture",
            RequiredTable("HUMBUGG_EMAIL_MESSAGES_TABLE"),
            (Environment.GetEnvironmentVariable("HUMBUGG_MAILER_BASE_URL") ??
                "http://host.docker.internal:8026").TrimEnd('/'),
            Environment.GetEnvironmentVariable("HUMBUGG_MAILER_AUTH_MODE") ?? "none",
            Environment.GetEnvironmentVariable("HUMBUGG_MAILER_SERVICE_ID") ?? "humbugg",
            Environment.GetEnvironmentVariable("HUMBUGG_APP_BUCKET") ?? "",
            (Environment.GetEnvironmentVariable("HUMBUGG_AVATAR_BASE_URL")?.TrimEnd('/')) ?? appBaseUrl,
            Environment.GetEnvironmentVariable("S3_ENDPOINT_URL"),
            RequiredTable("HUMBUGG_BILLING_TABLE"),
            RequiredTable("HUMBUGG_INVITATIONS_TABLE"));
    }

    // Table names are per-environment and carry no safe default: prod, each
    // developer's isolated dev stack, and any future environment all name them
    // differently. Substituting a guess for a missing variable points the
    // service at a table that does not exist and turns a misconfigured deploy
    // into a runtime failure far from its cause. Two of the names this used to
    // fall back to (humbugg-audit-events, humbugg-billing) were pre-rename
    // tables that have since been deleted outright.
    //
    // The deploy workflow sets all nine; dev-aws-setup.sh writes all nine
    // into humbugg/backend/.env from Terraform outputs. A missing one means the
    // environment is genuinely misconfigured, so fail at startup and say which.
    private static string RequiredTable(string variable) =>
        Environment.GetEnvironmentVariable(variable) is { } value && !string.IsNullOrWhiteSpace(value)
            ? value.Trim()
            : throw new InvalidOperationException(
                $"{variable} is not set. DynamoDB table names are per-environment and have no default. " +
                "In CI the deploy workflow sets it; locally run humbugg/scripts/dev-aws-setup.sh, " +
                "which writes the table names from Terraform outputs into humbugg/backend/.env.");

    // Local development runs two distinct browser origins against one backend: the Vite
    // marketing dev server on :5173 and the Expo web dev server on :8081.
    private static readonly string[] DefaultCorsOrigins =
        ["http://localhost:5173", "http://localhost:8081"];

    // CORS_ORIGINS is a comma-separated list because the surfaces that call this API live on
    // separate hosts (www., app., and both dev servers) and Lambda env vars are flat strings.
    private static string[] ParseCorsOrigins(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return DefaultCorsOrigins;
        var origins = value.Split(
            ',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        return origins.Length > 0 ? origins : DefaultCorsOrigins;
    }
}
