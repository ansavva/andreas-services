using Microsoft.AspNetCore.RateLimiting;
using System.Globalization;
using System.Threading.RateLimiting;

namespace Humbugg.Api.Services;

/// <summary>
/// A single fixed-window rate-limit rule: at most <see cref="PermitLimit"/> requests are allowed
/// per partition (per authenticated user, falling back to client IP) inside a rolling
/// <see cref="WindowSeconds"/> window. Limits are configuration, never hardcoded — every value is
/// read from the environment (populated from SSM at deploy time) with a safe default.
/// </summary>
public sealed record RateLimitRule(int PermitLimit, int WindowSeconds);

/// <summary>
/// The complete rate-limit specification for Humbugg. Abuse-sensitive actions each get a named
/// policy so a single account (or IP) cannot enumerate, spam invitations/reminders, or flood
/// account/group/payment creation. Rules cover both endpoints that exist today and endpoints that
/// are specified ahead of the feature landing (reminders, questions, payment sessions) so the
/// control is in place the moment those routes ship. Rate limiting is applied identically on every
/// plan — it is a security control, never a billing lever.
/// </summary>
public sealed record RateLimitSettings(
    bool Enabled,
    RateLimitRule Global,
    RateLimitRule AccountCreation,
    RateLimitRule GroupCreation,
    RateLimitRule Invitation,
    RateLimitRule Reminder,
    RateLimitRule Join,
    RateLimitRule Question,
    RateLimitRule PaymentSession)
{
    // Policy names referenced from controller [EnableRateLimiting(...)] attributes.
    public const string AccountCreationPolicy = "humbugg-account-creation";
    public const string GroupCreationPolicy = "humbugg-group-creation";
    public const string InvitationPolicy = "humbugg-invitation";
    public const string ReminderPolicy = "humbugg-reminder";
    public const string JoinPolicy = "humbugg-join";
    public const string QuestionPolicy = "humbugg-question";
    public const string PaymentSessionPolicy = "humbugg-payment-session";

    public static RateLimitSettings FromEnvironment() => new(
        Enabled: Flag("HUMBUGG_RATELIMIT_ENABLED", true),
        Global: Rule("HUMBUGG_RATELIMIT_GLOBAL", 300, 60),
        AccountCreation: Rule("HUMBUGG_RATELIMIT_ACCOUNT_CREATION", 5, 3600),
        GroupCreation: Rule("HUMBUGG_RATELIMIT_GROUP_CREATION", 20, 3600),
        Invitation: Rule("HUMBUGG_RATELIMIT_INVITATION", 30, 3600),
        Reminder: Rule("HUMBUGG_RATELIMIT_REMINDER", 10, 3600),
        Join: Rule("HUMBUGG_RATELIMIT_JOIN", 20, 3600),
        Question: Rule("HUMBUGG_RATELIMIT_QUESTION", 60, 3600),
        PaymentSession: Rule("HUMBUGG_RATELIMIT_PAYMENT_SESSION", 15, 3600));

    private static RateLimitRule Rule(string prefix, int defaultLimit, int defaultWindowSeconds) => new(
        PositiveInt($"{prefix}_LIMIT", defaultLimit),
        PositiveInt($"{prefix}_WINDOW_SECONDS", defaultWindowSeconds));

    private static bool Flag(string name, bool fallback)
    {
        var value = Environment.GetEnvironmentVariable(name);
        if (string.IsNullOrWhiteSpace(value)) return fallback;
        if (bool.TryParse(value, out var parsed)) return parsed;
        throw new InvalidOperationException($"{name} must be 'true' or 'false'.");
    }

    private static int PositiveInt(string name, int fallback)
    {
        var value = Environment.GetEnvironmentVariable(name);
        if (string.IsNullOrWhiteSpace(value)) return fallback;
        if (int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out var parsed) && parsed > 0) return parsed;
        throw new InvalidOperationException($"{name} must be a positive integer.");
    }
}

public static class RateLimiterConfiguration
{
    /// <summary>
    /// Registers the global backstop limiter plus every named policy. Partitioning is by
    /// authenticated Cognito subject so a limit follows the account across IPs; unauthenticated
    /// callers (which should already be rejected by auth) fall back to client IP. Rejections return
    /// a 429 in the standard Humbugg error envelope with a <c>Retry-After</c> header.
    /// </summary>
    public static IServiceCollection AddHumbuggRateLimiter(this IServiceCollection services, RateLimitSettings settings)
    {
        services.AddRateLimiter(options =>
        {
            options.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
            options.OnRejected = async (context, cancellationToken) =>
            {
                if (context.Lease.TryGetMetadata(MetadataName.RetryAfter, out var retryAfter))
                    context.HttpContext.Response.Headers.RetryAfter =
                        ((int)Math.Ceiling(retryAfter.TotalSeconds)).ToString(CultureInfo.InvariantCulture);
                context.HttpContext.Response.StatusCode = StatusCodes.Status429TooManyRequests;
                context.HttpContext.Response.ContentType = "application/json";
                await context.HttpContext.Response.WriteAsJsonAsync(
                    new { error = new { code = "rate_limited", message = "Too many requests. Please slow down and try again shortly." } },
                    cancellationToken);
            };

            if (!settings.Enabled)
                return;

            AddPolicy(options, RateLimitSettings.AccountCreationPolicy, settings.AccountCreation);
            AddPolicy(options, RateLimitSettings.GroupCreationPolicy, settings.GroupCreation);
            AddPolicy(options, RateLimitSettings.InvitationPolicy, settings.Invitation);
            AddPolicy(options, RateLimitSettings.ReminderPolicy, settings.Reminder);
            AddPolicy(options, RateLimitSettings.JoinPolicy, settings.Join);
            AddPolicy(options, RateLimitSettings.QuestionPolicy, settings.Question);
            AddPolicy(options, RateLimitSettings.PaymentSessionPolicy, settings.PaymentSession);

            options.GlobalLimiter = PartitionedRateLimiter.Create<HttpContext, string>(context =>
                RateLimitPartition.GetFixedWindowLimiter(PartitionKey(context), _ => Window(settings.Global)));
        });
        return services;
    }

    private static void AddPolicy(RateLimiterOptions options, string name, RateLimitRule rule) =>
        options.AddPolicy(name, context =>
            RateLimitPartition.GetFixedWindowLimiter(PartitionKey(context), _ => Window(rule)));

    private static FixedWindowRateLimiterOptions Window(RateLimitRule rule) => new()
    {
        PermitLimit = rule.PermitLimit,
        Window = TimeSpan.FromSeconds(rule.WindowSeconds),
        QueueLimit = 0,
        QueueProcessingOrder = QueueProcessingOrder.OldestFirst,
        AutoReplenishment = true
    };

    /// <summary>
    /// Prefer the Cognito subject so a limit tracks the account regardless of source IP; fall back to
    /// the first hop of X-Forwarded-For (API Gateway sets the client IP there) and finally the socket
    /// address. A stable per-partition prefix keeps the user and IP namespaces from colliding.
    /// </summary>
    internal static string PartitionKey(HttpContext context)
    {
        var subject = context.User.FindFirst("sub")?.Value;
        if (!string.IsNullOrEmpty(subject))
            return $"user:{subject}";
        var forwarded = context.Request.Headers["X-Forwarded-For"].FirstOrDefault();
        var clientIp = forwarded?.Split(',')[0].Trim();
        if (string.IsNullOrEmpty(clientIp))
            clientIp = context.Connection.RemoteIpAddress?.ToString();
        return $"ip:{clientIp ?? "unknown"}";
    }
}
