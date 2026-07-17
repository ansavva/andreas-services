namespace Humbugg.Api.Services;

/// <summary>
/// Stripe billing mode. Live mode is intentionally absent: activation is blocked
/// pending the merchant-identity review tracked in issue #159, so any attempt to
/// select it (or supply live credentials) fails fast during configuration load.
/// </summary>
public enum StripeMode
{
    /// <summary>No Stripe credentials wired; billing endpoints stay dormant.</summary>
    Disabled,

    /// <summary>Stripe test mode — the only mode permitted today.</summary>
    Test
}

/// <summary>
/// Configuration surface for Stripe billing. Every value is sourced from the
/// environment (never hardcoded constants) so product/price IDs, publishable and
/// secret keys, and the webhook signing secret all flow in from GitHub environment
/// secrets/vars and SSM at deploy time. Construction validates the configuration:
/// it fails fast when test mode is selected without the required credentials and
/// refuses any live-mode credential or mode.
/// </summary>
public sealed record StripeSettings
{
    private StripeSettings(StripeMode mode, string? publishableKey, string? secretKey, string? webhookSecret)
    {
        Mode = mode;
        PublishableKey = publishableKey;
        SecretKey = secretKey;
        WebhookSecret = webhookSecret;
    }

    public StripeMode Mode { get; }
    public string? PublishableKey { get; }
    public string? SecretKey { get; }
    public string? WebhookSecret { get; }

    /// <summary>True once test-mode credentials are configured and validated.</summary>
    public bool IsEnabled => Mode == StripeMode.Test;

    /// <summary>
    /// Builds and validates a <see cref="StripeSettings"/> from raw string values.
    /// Throws <see cref="InvalidOperationException"/> if live mode is requested,
    /// if any live credential is supplied, or if a required test-mode value is missing.
    /// </summary>
    public static StripeSettings Create(string? mode, string? publishableKey, string? secretKey, string? webhookSecret)
    {
        var settings = new StripeSettings(
            ParseMode(mode),
            Clean(publishableKey),
            Clean(secretKey),
            Clean(webhookSecret));
        settings.Validate();
        return settings;
    }

    public static StripeSettings FromEnvironment() => Create(
        Environment.GetEnvironmentVariable("HUMBUGG_STRIPE_MODE"),
        Environment.GetEnvironmentVariable("HUMBUGG_STRIPE_PUBLISHABLE_KEY"),
        Environment.GetEnvironmentVariable("HUMBUGG_STRIPE_SECRET_KEY"),
        Environment.GetEnvironmentVariable("HUMBUGG_STRIPE_WEBHOOK_SECRET"));

    private static StripeMode ParseMode(string? raw) => raw?.Trim().ToLowerInvariant() switch
    {
        null or "" or "disabled" or "off" => StripeMode.Disabled,
        "test" => StripeMode.Test,
        "live" => throw new InvalidOperationException(
            "Stripe live mode is blocked pending merchant-identity review (issue #159). " +
            "Set HUMBUGG_STRIPE_MODE=test until live-mode activation is approved."),
        _ => throw new InvalidOperationException(
            $"Unsupported HUMBUGG_STRIPE_MODE '{raw}'. Use 'test' or 'disabled'.")
    };

    private void Validate()
    {
        // Live credentials are never permitted, in any mode, until issue #159 is resolved.
        GuardNotLive(nameof(PublishableKey), PublishableKey, "pk_live_");
        GuardNotLive(nameof(SecretKey), SecretKey, "sk_live_");
        GuardNotLive(nameof(SecretKey), SecretKey, "rk_live_");

        if (Mode == StripeMode.Disabled)
            return;

        // Test mode: every credential is required and must be a Stripe test-mode value.
        RequireTestKey("HUMBUGG_STRIPE_PUBLISHABLE_KEY", PublishableKey, "pk_test_");
        RequireTestKey("HUMBUGG_STRIPE_SECRET_KEY", SecretKey, "sk_test_");
        RequireWebhookSecret("HUMBUGG_STRIPE_WEBHOOK_SECRET", WebhookSecret);
    }

    private static void GuardNotLive(string field, string? value, string livePrefix)
    {
        if (value is not null && value.StartsWith(livePrefix, StringComparison.Ordinal))
            throw new InvalidOperationException(
                $"A Stripe live-mode credential was supplied for {field}. Live mode is blocked " +
                "pending merchant-identity review (issue #159); only test-mode credentials are allowed.");
    }

    private static void RequireTestKey(string name, string? value, string testPrefix)
    {
        if (string.IsNullOrWhiteSpace(value))
            throw new InvalidOperationException(
                $"{name} is required when HUMBUGG_STRIPE_MODE=test but was not provided.");
        if (!value.StartsWith(testPrefix, StringComparison.Ordinal))
            throw new InvalidOperationException(
                $"{name} must be a Stripe test-mode key beginning with '{testPrefix}'.");
    }

    private static void RequireWebhookSecret(string name, string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
            throw new InvalidOperationException(
                $"{name} is required when HUMBUGG_STRIPE_MODE=test but was not provided.");
        if (!value.StartsWith("whsec_", StringComparison.Ordinal))
            throw new InvalidOperationException(
                $"{name} must be a Stripe webhook signing secret beginning with 'whsec_'.");
    }

    private static string? Clean(string? value) => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
