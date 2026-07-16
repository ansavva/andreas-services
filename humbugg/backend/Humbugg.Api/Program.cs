using Amazon.DynamoDBv2;
using Amazon.Lambda.AspNetCoreServer.Hosting;
using Humbugg.Api.Data;
using Humbugg.Api.Middleware;
using Humbugg.Api.Services;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Mvc;
using Microsoft.IdentityModel.Tokens;
using System.Text.Json;
using System.Text.Json.Serialization;

var builder = WebApplication.CreateBuilder(args);
var settings = HumbuggSettings.FromEnvironment();
builder.Services.AddSingleton(settings);
builder.Services.AddSingleton<IPlanCatalog>(PlanCatalog.FromEnvironment());

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
builder.Services.AddScoped<IProfileRepository, ProfileRepository>();
builder.Services.AddScoped<IGroupRepository, GroupRepository>();
builder.Services.AddScoped<IMembershipRepository, MembershipRepository>();
builder.Services.AddScoped<ICurrentUser, CurrentUser>();
builder.Services.AddScoped<IProfileService, ProfileService>();
builder.Services.AddScoped<IGroupService, GroupService>();
builder.Services.AddSingleton<IMatchingService, MatchingService>();
if (!string.IsNullOrWhiteSpace(settings.DynamoDbEndpointUrl))
    builder.Services.AddHostedService<DynamoDbBootstrap>();
builder.Services.AddAWSLambdaHosting(LambdaEventSource.HttpApi);

var app = builder.Build();
app.UseMiddleware<ApiExceptionMiddleware>();
app.UseCors();
app.UseAuthentication();
app.UseAuthorization();
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
    string AuditEventsTable)
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
        Environment.GetEnvironmentVariable("HUMBUGG_AUDIT_EVENTS_TABLE") ?? "humbugg-audit-events");
}
