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
builder.Services.AddCors(options => options.AddDefaultPolicy(policy =>
    policy.WithOrigins(settings.CorsOrigin).AllowAnyHeader().AllowAnyMethod()));

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
builder.Services.AddScoped<ITransactionalEmailService, TransactionalEmailService>();
builder.Services.AddScoped<IProfileRepository, ProfileRepository>();
builder.Services.AddScoped<IGroupRepository, GroupRepository>();
builder.Services.AddScoped<IMembershipRepository, MembershipRepository>();
builder.Services.AddScoped<IAuditRepository, AuditRepository>();
builder.Services.AddScoped<IAuditActorAnonymizer, AuditActorAnonymizer>();
builder.Services.AddScoped<IAnalyticsSink, DynamoDbAnalyticsSink>();
builder.Services.AddScoped<ICurrentUser, CurrentUser>();
builder.Services.AddScoped<IRequestCorrelation, HttpRequestCorrelation>();
builder.Services.AddScoped<IAuditTrail, AuditTrail>();
builder.Services.AddScoped<IProductAnalytics, ProductAnalytics>();
builder.Services.AddScoped<IProfileService, ProfileService>();
builder.Services.AddScoped<IGroupService, GroupService>();
builder.Services.AddScoped<IAccountDeletionService, AccountDeletionService>();
builder.Services.AddScoped<IDataExportService, DataExportService>();
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
    string CorsOrigin,
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
    string MailerServiceId = "humbugg")
{
    public static HumbuggSettings FromEnvironment() => new(
        Environment.GetEnvironmentVariable("AWS_REGION") ?? Environment.GetEnvironmentVariable("AWS_DEFAULT_REGION") ?? "us-east-1",
        Environment.GetEnvironmentVariable("COGNITO_REGION") ?? "us-east-1",
        Environment.GetEnvironmentVariable("COGNITO_USER_POOL_ID") ?? "us-east-1_example",
        Environment.GetEnvironmentVariable("COGNITO_CLIENT_ID") ?? "humbugg-web",
        Environment.GetEnvironmentVariable("CORS_ORIGIN") ?? "http://localhost:5173",
        (Environment.GetEnvironmentVariable("APP_BASE_URL") ?? "http://localhost:5173").TrimEnd('/'),
        Environment.GetEnvironmentVariable("DYNAMODB_ENDPOINT_URL"),
        Environment.GetEnvironmentVariable("HUMBUGG_PROFILES_TABLE") ?? "humbugg-profiles",
        Environment.GetEnvironmentVariable("HUMBUGG_GROUPS_TABLE") ?? "humbugg-groups",
        Environment.GetEnvironmentVariable("HUMBUGG_GROUPMEMBERS_TABLE") ?? "humbugg-groupmembers",
        Environment.GetEnvironmentVariable("HUMBUGG_DRAWS_TABLE") ?? "humbugg-draws",
        Environment.GetEnvironmentVariable("HUMBUGG_AUDIT_EVENTS_TABLE") ?? "humbugg-audit-events",
        Environment.GetEnvironmentVariable("HUMBUGG_ANALYTICS_EVENTS_TABLE") ?? "humbugg-analytics-events",
        Environment.GetEnvironmentVariable("HUMBUGG_EMAIL_PROVIDER") ?? "capture",
        Environment.GetEnvironmentVariable("HUMBUGG_EMAIL_MESSAGES_TABLE") ?? "humbugg-email-messages",
        (Environment.GetEnvironmentVariable("HUMBUGG_MAILER_BASE_URL") ??
            "http://host.docker.internal:8026").TrimEnd('/'),
        Environment.GetEnvironmentVariable("HUMBUGG_MAILER_AUTH_MODE") ?? "none",
        Environment.GetEnvironmentVariable("HUMBUGG_MAILER_SERVICE_ID") ?? "humbugg");
}
