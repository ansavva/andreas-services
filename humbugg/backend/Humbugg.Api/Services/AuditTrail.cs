using Humbugg.Api.Data;
using Humbugg.Api.Models;
using System.Diagnostics;

namespace Humbugg.Api.Services;

/// <summary>
/// The single entry point for recording security- and privacy-relevant exchange actions.
/// Every event captures the actor, action, target, group (or organization), timestamp, and
/// request correlation id. All caller-supplied metadata is passed through
/// <see cref="AuditRedaction"/> before it is persisted, so sensitive values, addresses,
/// invite secrets, tokens, and assignment contents can never be written to the audit log.
/// The write is awaited and its failures propagate: an audited action cannot silently fail.
/// </summary>
public interface IAuditTrail
{
    Task RecordAsync(
        AuditAction action,
        string groupId,
        AuditTarget target,
        IReadOnlyDictionary<string, string>? metadata = null,
        string? organizationId = null,
        CancellationToken cancellationToken = default);
}

internal sealed class AuditTrail(
    ICurrentUser user,
    IRequestCorrelation correlation,
    IAuditRepository repository) : IAuditTrail
{
    public Task RecordAsync(
        AuditAction action,
        string groupId,
        AuditTarget target,
        IReadOnlyDictionary<string, string>? metadata = null,
        string? organizationId = null,
        CancellationToken cancellationToken = default)
    {
        var now = DateTimeOffset.UtcNow.ToString("O");
        var auditEvent = new AuditEvent(
            groupId,
            $"{now}#{Guid.NewGuid()}",
            action,
            user.UserId,
            target.Type,
            target.Id,
            organizationId,
            correlation.CorrelationId,
            now,
            AuditRedaction.Redact(metadata));
        return repository.AppendAsync(auditEvent, cancellationToken);
    }
}

/// <summary>
/// Enforces the redaction guarantee: any metadata whose key names a sensitive field, or whose
/// value looks like a secret, invite link, or token, is replaced with <see cref="Placeholder"/>
/// before it reaches the audit log. Callers cannot opt out — <see cref="Redact"/> is the only
/// path metadata takes into an <see cref="AuditEvent"/>.
/// </summary>
public static class AuditRedaction
{
    public const string Placeholder = "[redacted]";

    // Substrings that mark a metadata key as carrying sensitive content. Matching is
    // case-insensitive and partial, so "shipping_address" or "invite_secret" are caught.
    private static readonly string[] SensitiveKeyFragments =
    [
        "address", "line1", "line2", "street", "postal", "zip", "city", "region", "country",
        "wishlist", "wish", "avoid", "invite", "secret", "token", "assignment", "recipient",
        "giver", "email", "phone", "password", "hash"
    ];

    public static bool IsSensitiveKey(string key) =>
        SensitiveKeyFragments.Any(fragment => key.Contains(fragment, StringComparison.OrdinalIgnoreCase));

    /// <summary>
    /// Values that carry an invite link or a long, high-entropy token are redacted even under a
    /// benign key name, so a stray secret can never leak into the audit log by mislabelling.
    /// </summary>
    public static bool IsSensitiveValue(string value)
    {
        if (value.Contains("#invite=", StringComparison.OrdinalIgnoreCase)) return true;
        if (value.Contains("/join/", StringComparison.OrdinalIgnoreCase)) return true;
        var trimmed = value.Trim();
        // A long, unbroken run of URL-safe base64 characters is almost certainly a secret/token.
        return trimmed.Length >= 24
            && !trimmed.Contains(' ', StringComparison.Ordinal)
            && trimmed.All(character => char.IsLetterOrDigit(character) || character is '-' or '_')
            && trimmed.Count(char.IsDigit) >= 4;
    }

    public static IReadOnlyDictionary<string, string> Redact(IReadOnlyDictionary<string, string>? metadata)
    {
        if (metadata is null || metadata.Count == 0)
            return new Dictionary<string, string>(StringComparer.Ordinal);
        var redacted = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var (key, value) in metadata)
            redacted[key] = IsSensitiveKey(key) || IsSensitiveValue(value) ? Placeholder : value;
        return redacted;
    }
}

/// <summary>Supplies the request correlation id recorded on every audit event.</summary>
internal interface IRequestCorrelation
{
    string CorrelationId { get; }
}

internal sealed class HttpRequestCorrelation(IHttpContextAccessor accessor) : IRequestCorrelation
{
    public string CorrelationId
    {
        get
        {
            var context = accessor.HttpContext;
            if (context is not null)
            {
                var trace = context.Request.Headers["X-Amzn-Trace-Id"].FirstOrDefault();
                if (!string.IsNullOrWhiteSpace(trace)) return trace;
                if (!string.IsNullOrWhiteSpace(context.TraceIdentifier)) return context.TraceIdentifier;
            }
            return Activity.Current?.Id ?? "unknown";
        }
    }
}
