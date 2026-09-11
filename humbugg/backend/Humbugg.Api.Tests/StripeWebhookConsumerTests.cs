using Humbugg.Api.Consumers.StripeWebhooks;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Microsoft.Extensions.Logging.Abstractions;
using System.Text;
using System.Text.Json;
using Xunit;
using static Humbugg.Api.Consumers.StripeWebhooks.AwsLambdaStripeWebhookConsumer;

namespace Humbugg.Api.Tests;

// The consumer's one decision per message: consumed, or returned to the queue. Each branch traced
// to the reason it exists — the receiver's envelope, another machine's event in a shared sandbox,
// the charge-before-session ordering race, and the refusals a retry cannot change.
public sealed class StripeWebhookConsumerTests
{
    [Fact]
    public async Task AppliesAnEventForThisEnvironmentThroughTheQueuedPath()
    {
        var billing = new FakeBilling();
        var consumer = Consumer(billing, "dev-abc");

        var outcome = await consumer.ConsumeOneAsync(Envelope(StripeEvent("dev-abc"), "t=1,v1=sig"), "m1");

        Assert.Equal(Outcome.Done, outcome);
        Assert.Equal("t=1,v1=sig", billing.QueuedSignature);
        Assert.Null(billing.DirectSignature);
    }

    [Fact]
    public async Task DropsAnotherMachinesEventWithoutTouchingBilling()
    {
        var billing = new FakeBilling();
        var consumer = Consumer(billing, "dev-abc");

        var outcome = await consumer.ConsumeOneAsync(Envelope(StripeEvent("dev-xyz"), "t=1,v1=sig"), "m1");

        Assert.Equal(Outcome.Done, outcome);
        Assert.Null(billing.QueuedSignature);
    }

    [Fact]
    public async Task ForwardsAnEventWithNoEnvironmentAndLetsBillingDecide()
    {
        var billing = new FakeBilling();
        var consumer = Consumer(billing, "dev-abc");

        await consumer.ConsumeOneAsync(Envelope("""{"id":"evt_1","type":"charge.refunded","data":{"object":{}}}""", "t=1,v1=sig"), "m1");

        Assert.Equal("t=1,v1=sig", billing.QueuedSignature);
    }

    [Fact]
    public async Task RetriesTheChargeBeforeSessionRace()
    {
        var billing = new FakeBilling { Throws = ApiException.Conflict("Stripe charge arrived before its Checkout Session was confirmed.") };

        var outcome = await Consumer(billing, "production").ConsumeOneAsync(Envelope(StripeEvent("production"), "t=1,v1=sig"), "m1");

        Assert.Equal(Outcome.Retry, outcome);
    }

    [Fact]
    public async Task ConsumesABodyTheServiceWillNeverAccept()
    {
        var billing = new FakeBilling { Throws = ApiException.BadRequest("Invalid Stripe webhook: signature mismatch") };

        var outcome = await Consumer(billing, "production").ConsumeOneAsync(Envelope(StripeEvent("production"), "t=1,v1=bad"), "m1");

        Assert.Equal(Outcome.Done, outcome);
    }

    [Fact]
    public async Task RetriesAnInfrastructureFailure()
    {
        var billing = new FakeBilling { Throws = new TimeoutException("DynamoDB") };

        var outcome = await Consumer(billing, "production").ConsumeOneAsync(Envelope(StripeEvent("production"), "t=1,v1=sig"), "m1");

        Assert.Equal(Outcome.Retry, outcome);
    }

    [Theory]
    [InlineData("not json")]
    [InlineData("""{"signature":"t=1,v1=sig"}""")]
    [InlineData("""{"signature":"t=1,v1=sig","body_b64":"%%%"}""")]
    public async Task ConsumesAMessageThatIsNotTheReceiversEnvelope(string messageBody)
    {
        var billing = new FakeBilling();

        var outcome = await Consumer(billing, "production").ConsumeOneAsync(messageBody, "m1");

        Assert.Equal(Outcome.Done, outcome);
        Assert.Null(billing.QueuedSignature);
    }

    private static AwsLambdaStripeWebhookConsumer Consumer(IBillingService billing, string environment) =>
        new(billing, environment, NullLogger<AwsLambdaStripeWebhookConsumer>.Instance);

    private static string StripeEvent(string environment) =>
        """{"id":"evt_1","type":"checkout.session.completed","data":{"object":{"metadata":{"environment":"ENV"}}}}"""
            .Replace("ENV", environment);

    private static string Envelope(string payload, string signature) => JsonSerializer.Serialize(new
    {
        signature,
        body_b64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(payload)),
        received_at = "2026-09-11T00:00:00Z",
    });

    private sealed class FakeBilling : IBillingService
    {
        public Exception? Throws { get; init; }
        public string? QueuedSignature { get; private set; }
        public string? DirectSignature { get; private set; }

        public Task<CheckoutResponse> CreatePlusCheckoutAsync(string groupId, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<PlusPurchaseStatus> GetPlusStatusAsync(string groupId, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task ProcessWebhookAsync(string payload, string signature, CancellationToken cancellationToken = default)
        {
            DirectSignature = signature;
            return Task.CompletedTask;
        }

        public Task ProcessQueuedWebhookAsync(string payload, string signature, CancellationToken cancellationToken = default)
        {
            QueuedSignature = signature;
            return Throws is null ? Task.CompletedTask : Task.FromException(Throws);
        }
    }
}
