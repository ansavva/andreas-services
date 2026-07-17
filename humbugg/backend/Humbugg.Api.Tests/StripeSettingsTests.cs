using Humbugg.Api.Services;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class StripeSettingsTests
{
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("  ")]
    [InlineData("disabled")]
    [InlineData("DISABLED")]
    [InlineData("off")]
    public void MissingOrDisabledModeYieldsDisabledSettings(string? mode)
    {
        var settings = StripeSettings.Create(mode, null, null, null);

        Assert.Equal(StripeMode.Disabled, settings.Mode);
        Assert.False(settings.IsEnabled);
    }

    [Fact]
    public void TestModeWithCompleteCredentialsIsEnabled()
    {
        var settings = StripeSettings.Create(
            "test",
            " pk_test_publishable ",
            "sk_test_secret",
            "whsec_test_signing");

        Assert.Equal(StripeMode.Test, settings.Mode);
        Assert.True(settings.IsEnabled);
        // Values are trimmed and surfaced from configuration, never hardcoded constants.
        Assert.Equal("pk_test_publishable", settings.PublishableKey);
        Assert.Equal("sk_test_secret", settings.SecretKey);
        Assert.Equal("whsec_test_signing", settings.WebhookSecret);
    }

    [Fact]
    public void LiveModeIsBlockedPendingMerchantReview()
    {
        var error = Assert.Throws<InvalidOperationException>(() =>
            StripeSettings.Create("live", "pk_test_x", "sk_test_x", "whsec_x"));

        Assert.Contains("#159", error.Message);
    }

    [Theory]
    [InlineData("pk_live_abc", "sk_test_x", "whsec_x")]
    [InlineData("pk_test_x", "sk_live_abc", "whsec_x")]
    [InlineData("pk_test_x", "rk_live_abc", "whsec_x")]
    public void LiveCredentialsAreRejectedEvenInTestMode(string publishable, string secret, string webhook)
    {
        var error = Assert.Throws<InvalidOperationException>(() =>
            StripeSettings.Create("test", publishable, secret, webhook));

        Assert.Contains("#159", error.Message);
    }

    [Fact]
    public void LiveCredentialsAreRejectedEvenWhenDisabled()
    {
        Assert.Throws<InvalidOperationException>(() =>
            StripeSettings.Create("disabled", null, "sk_live_abc", null));
    }

    [Theory]
    [InlineData(null, "sk_test_x", "whsec_x")]
    [InlineData("pk_test_x", null, "whsec_x")]
    [InlineData("pk_test_x", "sk_test_x", null)]
    public void TestModeFailsFastWhenRequiredCredentialMissing(string? publishable, string? secret, string? webhook)
    {
        Assert.Throws<InvalidOperationException>(() =>
            StripeSettings.Create("test", publishable, secret, webhook));
    }

    [Theory]
    [InlineData("pk_bad_x", "sk_test_x", "whsec_x")]
    [InlineData("pk_test_x", "sk_bad_x", "whsec_x")]
    [InlineData("pk_test_x", "sk_test_x", "bad_x")]
    public void TestModeRejectsCredentialsWithTheWrongPrefix(string publishable, string secret, string webhook)
    {
        Assert.Throws<InvalidOperationException>(() =>
            StripeSettings.Create("test", publishable, secret, webhook));
    }

    [Fact]
    public void UnknownModeIsRejected()
    {
        Assert.Throws<InvalidOperationException>(() =>
            StripeSettings.Create("sandbox", null, null, null));
    }
}
