using Humbugg.Api.Data;
using Humbugg.Api.Models;

namespace Humbugg.Api.Services;

/// <summary>
/// The single entry point for emitting privacy-safe product-analytics events. Callers describe a
/// funnel milestone with a plan, a group surrogate key, a deterministic idempotency key, and an
/// optional bag of aggregate dimensions. Emission is <b>best-effort telemetry</b>: it never throws
/// into the request path, so a failing analytics sink can never break a user action. It is also
/// <b>authoritative and server-side</b> — events originate here on the server, never from a client
/// call, which is what makes them trustworthy for security- and payment-sensitive steps.
/// </summary>
public interface IProductAnalytics
{
    Task TrackAsync(
        AnalyticsEventType type,
        PlanCode plan,
        string groupId,
        string idempotencyKey,
        IReadOnlyDictionary<string, string>? dimensions = null,
        CancellationToken cancellationToken = default);
}

/// <summary>Configuration for product analytics, resolved from the environment.</summary>
public sealed record AnalyticsOptions(bool Enabled)
{
    /// <summary>
    /// Analytics is opt-out: it is on unless <c>HUMBUGG_ANALYTICS_ENABLED</c> is explicitly set to a
    /// false-y value. When disabled, <see cref="ProductAnalytics.TrackAsync"/> short-circuits before
    /// building or writing any event, so no analytics data is produced at all.
    /// </summary>
    public static AnalyticsOptions FromEnvironment()
    {
        var raw = Environment.GetEnvironmentVariable("HUMBUGG_ANALYTICS_ENABLED");
        var enabled = string.IsNullOrWhiteSpace(raw)
            || !(raw.Equals("false", StringComparison.OrdinalIgnoreCase)
                || raw.Equals("0", StringComparison.Ordinal)
                || raw.Equals("off", StringComparison.OrdinalIgnoreCase)
                || raw.Equals("no", StringComparison.OrdinalIgnoreCase));
        return new AnalyticsOptions(enabled);
    }
}

internal sealed class ProductAnalytics(
    IAnalyticsSink sink,
    AnalyticsOptions options,
    ILogger<ProductAnalytics> logger) : IProductAnalytics
{
    public async Task TrackAsync(
        AnalyticsEventType type,
        PlanCode plan,
        string groupId,
        string idempotencyKey,
        IReadOnlyDictionary<string, string>? dimensions = null,
        CancellationToken cancellationToken = default)
    {
        // The disable switch short-circuits before any event is built or written.
        if (!options.Enabled) return;

        var evt = new AnalyticsEvent(
            type,
            plan,
            groupId,
            idempotencyKey,
            DateTimeOffset.UtcNow.ToString("O"),
            AnalyticsDimensions.Sanitize(dimensions));

        // A structured, redacted log line gives a zero-infrastructure internal reporting path
        // (CloudWatch Logs Insights); see humbugg/docs/analytics.md.
        logger.LogInformation(
            "analytics_event type={EventType} plan={Plan} group={GroupId} dimensions={Dimensions}",
            evt.EventType, evt.Plan, evt.GroupId, evt.Dimensions);

        try
        {
            await sink.RecordAsync(evt, cancellationToken);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            // Analytics is best-effort: never fail the user's action because telemetry could not
            // be persisted. Duplicate suppression is handled inside the sink, not here.
            logger.LogWarning(ex, "Dropping analytics event {EventType} for group {GroupId}", type, groupId);
        }
    }
}

/// <summary>
/// The allow-list layer that guarantees analytics events carry only aggregate, non-identifying
/// dimensions. Enforcement is two-sided:
/// <list type="number">
/// <item>a key is dropped unless it is on the explicit <see cref="Allowed"/> allow-list, so a new
/// prohibited field can never leak in by default;</item>
/// <item>even an allow-listed key is dropped if its value trips the shared
/// <see cref="AuditRedaction"/> secret/token detector, so a stray token can never ride in under a
/// benign name.</item>
/// </list>
/// Reusing <see cref="AuditRedaction"/> keeps a single source of truth for what "sensitive" means
/// across both the audit and analytics streams.
/// </summary>
public static class AnalyticsDimensions
{
    /// <summary>
    /// Every dimension key analytics is allowed to record. All values are aggregate counts, plan
    /// codes, billing cadences, or day spans — never free text, contact details, or secrets.
    /// </summary>
    public static readonly IReadOnlySet<string> Allowed = new HashSet<string>(StringComparer.Ordinal)
    {
        "participant_count",
        "member_count",
        "ready_count",
        "exclusion_count",
        "is_repeat",
        "plan_from",
        "plan_to",
        "billing_cadence",
        "days_to_draw",
    };

    public static bool IsAllowed(string key) => Allowed.Contains(key);

    public static IReadOnlyDictionary<string, string> Sanitize(IReadOnlyDictionary<string, string>? dimensions)
    {
        var clean = new Dictionary<string, string>(StringComparer.Ordinal);
        if (dimensions is null || dimensions.Count == 0) return clean;
        foreach (var (key, value) in dimensions)
        {
            // Drop anything not explicitly allowed, anything a sensitive key fragment matches, and
            // anything whose value looks like a secret/token/invite link.
            if (!IsAllowed(key)) continue;
            if (AuditRedaction.IsSensitiveKey(key)) continue;
            if (AuditRedaction.IsSensitiveValue(value)) continue;
            clean[key] = value;
        }
        return clean;
    }
}
