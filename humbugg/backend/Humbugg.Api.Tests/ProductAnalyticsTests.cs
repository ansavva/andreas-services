using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class ProductAnalyticsTests
{
    // ─── Prohibited-field redaction: the privacy guarantee ───────────────────

    [Theory]
    [InlineData("recipient_wishlist")]
    [InlineData("wishlist")]
    [InlineData("shipping_address")]
    [InlineData("line1")]
    [InlineData("postal_code")]
    [InlineData("email")]
    [InlineData("invite_token")]
    [InlineData("invite_secret")]
    [InlineData("assignment")]
    [InlineData("giver")]
    [InlineData("recipient")]
    public void SanitizeDropsEveryProhibitedField(string prohibitedKey)
    {
        var clean = AnalyticsDimensions.Sanitize(new Dictionary<string, string>
        {
            [prohibitedKey] = "a bicycle for santa@example.com at 10 Downing Street",
            ["participant_count"] = "5"
        });

        Assert.False(clean.ContainsKey(prohibitedKey));
        Assert.Equal("5", clean["participant_count"]);
    }

    [Fact]
    public void SanitizeDropsUnknownKeysNotOnTheAllowList()
    {
        var clean = AnalyticsDimensions.Sanitize(new Dictionary<string, string>
        {
            ["surprise_new_field"] = "anything",
            ["plan_to"] = "plus"
        });

        Assert.False(clean.ContainsKey("surprise_new_field"));
        Assert.Equal("plus", clean["plan_to"]);
    }

    [Fact]
    public void SanitizeDropsSecretLookingValuesEvenUnderAllowListedKeys()
    {
        // "days_to_draw" is allow-listed, but a high-entropy token value must never survive.
        var clean = AnalyticsDimensions.Sanitize(new Dictionary<string, string>
        {
            ["days_to_draw"] = "kR3nQ9zX1mP4wL7vB2cD8fG5hJ0tY6sA",
            ["participant_count"] = "3"
        });

        Assert.False(clean.ContainsKey("days_to_draw"));
        Assert.Equal("3", clean["participant_count"]);
    }

    [Fact]
    public async Task TrackedEventNeverPersistsProhibitedDimensions()
    {
        var sink = new CapturingSink();
        var subject = new ProductAnalytics(sink, new AnalyticsOptions(true), NullLogger<ProductAnalytics>.Instance);

        await subject.TrackAsync(AnalyticsEventType.DrawCompleted, PlanCode.Plus, "group-1", "draw_completed:group-1",
            new Dictionary<string, string>
            {
                ["participant_count"] = "8",
                ["recipient_address"] = "10 Downing Street",
                ["assignment"] = "a -> b",
                ["email"] = "santa@example.com"
            }, TestContext.Current.CancellationToken);

        var saved = Assert.Single(sink.Saved);
        Assert.Equal("8", saved.Dimensions["participant_count"]);
        Assert.DoesNotContain("recipient_address", saved.Dimensions.Keys);
        Assert.DoesNotContain("assignment", saved.Dimensions.Keys);
        Assert.DoesNotContain("email", saved.Dimensions.Keys);
        // No prohibited class of value survives anywhere in the persisted dimensions.
        Assert.All(saved.Dimensions.Values, value => Assert.DoesNotContain("@", value));
    }

    // ─── Recorded shape: plan + surrogate group id + aggregate dimensions ────

    [Fact]
    public async Task TrackedEventRecordsPlanGroupTypeAndTimestamp()
    {
        var sink = new CapturingSink();
        var subject = new ProductAnalytics(sink, new AnalyticsOptions(true), NullLogger<ProductAnalytics>.Instance);

        await subject.TrackAsync(AnalyticsEventType.GroupCreated, PlanCode.Work, "group-9", "group_created:group-9",
            cancellationToken: TestContext.Current.CancellationToken);

        var saved = Assert.Single(sink.Saved);
        Assert.Equal(AnalyticsEventType.GroupCreated, saved.EventType);
        Assert.Equal(PlanCode.Work, saved.Plan);
        Assert.Equal("group-9", saved.GroupId);
        Assert.Equal("group_created:group-9", saved.IdempotencyKey);
        Assert.False(string.IsNullOrWhiteSpace(saved.OccurredAt));
    }

    // ─── The disable switch stops all emission ───────────────────────────────

    [Fact]
    public async Task DisabledAnalyticsEmitsNothing()
    {
        var sink = new CapturingSink();
        var subject = new ProductAnalytics(sink, new AnalyticsOptions(false), NullLogger<ProductAnalytics>.Instance);

        await subject.TrackAsync(AnalyticsEventType.GroupCreated, PlanCode.Free, "group-1", "group_created:group-1",
            cancellationToken: TestContext.Current.CancellationToken);

        Assert.Empty(sink.Saved);
    }

    [Theory]
    [InlineData("false", false)]
    [InlineData("0", false)]
    [InlineData("off", false)]
    [InlineData("no", false)]
    [InlineData("true", true)]
    [InlineData("1", true)]
    [InlineData(null, true)]
    [InlineData("", true)]
    public void EnabledFlagIsOptOut(string? raw, bool expected)
    {
        Environment.SetEnvironmentVariable("HUMBUGG_ANALYTICS_ENABLED", raw);
        try
        {
            Assert.Equal(expected, AnalyticsOptions.FromEnvironment().Enabled);
        }
        finally
        {
            Environment.SetEnvironmentVariable("HUMBUGG_ANALYTICS_ENABLED", null);
        }
    }

    // ─── Emission is best-effort: a failing sink never breaks the request ────

    [Fact]
    public async Task FailingSinkDoesNotThrowIntoTheRequestPath()
    {
        var subject = new ProductAnalytics(new ThrowingSink(), new AnalyticsOptions(true), NullLogger<ProductAnalytics>.Instance);

        // Must complete without throwing — analytics is telemetry, not a protected write.
        await subject.TrackAsync(AnalyticsEventType.DrawCompleted, PlanCode.Free, "group-1", "draw_completed:group-1",
            cancellationToken: TestContext.Current.CancellationToken);
    }

    // ─── The model covers the whole funnel ───────────────────────────────────

    [Fact]
    public void EventModelCoversTheWholeFunnel()
    {
        var types = Enum.GetValues<AnalyticsEventType>();
        AnalyticsEventType[] required =
        [
            AnalyticsEventType.GroupCreated, AnalyticsEventType.InviteSent, AnalyticsEventType.ParticipantJoined,
            AnalyticsEventType.ParticipantReady, AnalyticsEventType.DrawCompleted, AnalyticsEventType.AssignmentViewed,
            AnalyticsEventType.GiftSent, AnalyticsEventType.GiftReceived, AnalyticsEventType.PlanUpgraded,
            AnalyticsEventType.SubscriptionRenewed, AnalyticsEventType.SubscriptionCancelled,
            AnalyticsEventType.RepeatExchangeCreated
        ];
        Assert.All(required, type => Assert.Contains(type, types));
    }

    [Theory]
    [InlineData(AnalyticsEventType.GroupCreated, "group_created")]
    [InlineData(AnalyticsEventType.DrawCompleted, "draw_completed")]
    [InlineData(AnalyticsEventType.RepeatExchangeCreated, "repeat_exchange_created")]
    public void EventTypesSerializeToSnakeCaseWireForm(AnalyticsEventType type, string expected) =>
        Assert.Equal(expected, DynamoDbAnalyticsSink.Wire(type));

    private sealed class CapturingSink : IAnalyticsSink
    {
        public List<AnalyticsEvent> Saved { get; } = [];
        public Task RecordAsync(AnalyticsEvent analyticsEvent, CancellationToken cancellationToken = default)
        {
            Saved.Add(analyticsEvent);
            return Task.CompletedTask;
        }
    }

    private sealed class ThrowingSink : IAnalyticsSink
    {
        public Task RecordAsync(AnalyticsEvent analyticsEvent, CancellationToken cancellationToken = default) =>
            throw new InvalidOperationException("sink unavailable");
    }
}
