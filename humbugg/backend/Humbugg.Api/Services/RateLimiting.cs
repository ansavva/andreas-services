using Microsoft.AspNetCore.RateLimiting;
using System.Globalization;
using System.Threading.RateLimiting;

namespace Humbugg.Api.Services;

/// <summary>
/// A single fixed-window rate-limit rule: at most <see cref="PermitLimit"/> requests are allowed
/// per partition (per authenticated user, falling back to trusted client IP) inside a rolling
/// <see cref="WindowSeconds"/> window. Values are configuration, never hardcoded — every value is
/// read from the environment (populated from SSM at deploy time) with a safe default.
/// </summary>
public sealed record RateLimitRule(int PermitLimit, int WindowSeconds);

/// <summary>
/// Humbugg applies ONE uniform rate limit to every endpoint. There are deliberately no
/// endpoint-specific policies: an attacker could come from any route, so every request — read or
/// write, known abuse vector or not — counts against the same per-caller budget. The limit is
/// applied identically on every plan; it is a security control, never a billing lever.
/// </summary>
public sealed record RateLimitSettings(bool Enabled, RateLimitRule Global)
{
    public static RateLimitSettings FromEnvironment() => new(
        Enabled: Flag("HUMBUGG_RATELIMIT_ENABLED", true),
        Global: Rule("HUMBUGG_RATELIMIT_GLOBAL", 300, 60));

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
    /// Registers a single global limiter that covers EVERY endpoint (it applies without any
    /// per-endpoint attribute). Partitioning is by authenticated Cognito subject so a limit follows
    /// the account across IPs; unauthenticated callers fall back to the trusted client IP. Rejections
    /// return a 429 in the standard Humbugg error envelope with a <c>Retry-After</c> header.
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

            options.GlobalLimiter = PartitionedRateLimiter.Create<HttpContext, string>(context =>
                RateLimitPartition.GetFixedWindowLimiter(PartitionKey(context), _ => Window(settings.Global)));
        });
        return services;
    }

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
    /// the connection's remote IP, which the API Gateway Lambda integration populates from the trusted
    /// request-context <c>sourceIp</c>. We deliberately do NOT read the <c>X-Forwarded-For</c> header:
    /// its left-most hop is supplied by the caller and is spoofable behind API Gateway, so trusting it
    /// would let an attacker rotate the header to mint unlimited IP partitions and evade the per-IP
    /// limit on unauthenticated endpoints. A stable per-partition prefix keeps the user and IP
    /// namespaces from colliding.
    /// </summary>
    internal static string PartitionKey(HttpContext context)
    {
        var subject = context.User.FindFirst("sub")?.Value;
        if (!string.IsNullOrEmpty(subject))
            return $"user:{subject}";
        var clientIp = context.Connection.RemoteIpAddress?.ToString();
        return $"ip:{clientIp ?? "unknown"}";
    }
}
