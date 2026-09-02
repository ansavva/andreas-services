using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using System.Security.Cryptography;
using System.Text;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class BillingServiceTests
{
    [Fact]
    public async Task CheckoutCreatesConfiguredOneTimePurchaseForOwner()
    {
        var world = World();

        var result = await world.Subject.CreatePlusCheckoutAsync("group-1", TestContext.Current.CancellationToken);

        Assert.Equal("https://checkout.stripe.test/session", result.CheckoutUrl);
        Assert.Equal(PaymentStatus.Pending, result.Status);
        Assert.NotNull(world.Billing.Created);
        Assert.Equal(1_200, world.Billing.Created.AmountCents);
        Assert.Equal("price_plus", world.Stripe.Request!.PriceId);
        Assert.Equal("group-1", world.Stripe.Request.GroupId);
        Assert.Equal("owner", world.Stripe.Request.UserId);
        Assert.Contains("checkout=success", world.Stripe.Request.SuccessUrl);
        Assert.Contains("checkout=canceled", world.Stripe.Request.CancelUrl);
    }

    // Both returns land on the product app's organizer billing area. Pinned because the previous
    // shape — `{APP_BASE_URL}/app/groups/{id}` — was left over from the app being served under
    // www.humbugg.com/app: only the marketing origin 301s that, and APP_BASE_URL is the app's own
    // origin, so every paid return went to the not-found screen and the purchase looked lost.
    [Fact]
    public async Task CheckoutReturnsToTheOrganizerBillingArea()
    {
        var world = World();

        await world.Subject.CreatePlusCheckoutAsync("group-1", TestContext.Current.CancellationToken);

        Assert.StartsWith("https://humbugg.test/organize/group-1?", world.Stripe.Request!.SuccessUrl);
        Assert.Equal("https://humbugg.test/organize/group-1?checkout=canceled", world.Stripe.Request.CancelUrl);
        Assert.DoesNotContain("/app/", world.Stripe.Request.SuccessUrl);
    }

    [Fact]
    public async Task CheckoutRejectsNonOwnerAndExistingEntitlement()
    {
        var notOwner = World(userId: "stranger");
        Assert.Equal("forbidden",
            (await Assert.ThrowsAsync<ApiException>(() => notOwner.Subject.CreatePlusCheckoutAsync(
                "group-1", TestContext.Current.CancellationToken))).Code);

        var upgraded = World(plan: PlanCode.Plus, entitlementId: "plus:group-1");
        Assert.Equal("conflict",
            (await Assert.ThrowsAsync<ApiException>(() => upgraded.Subject.CreatePlusCheckoutAsync(
                "group-1", TestContext.Current.CancellationToken))).Code);
    }

    [Fact]
    public async Task CheckoutRetryRecoversReservedAttemptWithoutOpeningDuplicate()
    {
        var world = World();
        world.Billing.ReserveResult = false;
        world.Billing.Latest = new PaymentRecord(
            "purchase-1", "group-1", "owner", "", "", null, "price_plus", 1_200,
            "USD", "test", PaymentStatus.Pending, null, "now", "now");

        await world.Subject.CreatePlusCheckoutAsync("group-1", TestContext.Current.CancellationToken);

        Assert.Equal("purchase-1", world.Stripe.Request!.PurchaseId);
        Assert.Equal("cs_test_1", world.Billing.Latest.CheckoutSessionId);
    }

    [Fact]
    public async Task VerifiedWebhookIsDelegatedToIdempotentBillingStore()
    {
        var world = World();
        var webhook = new BillingWebhookEvent(
            "evt_1", "group-1", "group-1", "owner", "cs_1", "pi_1", "price_plus",
            1_200, "USD", "test", PaymentStatus.Paid, null, "now");
        world.Stripe.Webhook = webhook;

        await world.Subject.ProcessWebhookAsync(
            "{}", "valid-signature", TestContext.Current.CancellationToken);

        Assert.Same(webhook, world.Billing.Applied);
        Assert.Equal(("{}", "valid-signature"), world.Stripe.Parsed);
    }

    [Fact]
    public async Task StatusReturnsLatestPaymentAndEntitlement()
    {
        var world = World(plan: PlanCode.Plus, entitlementId: "plus:group-1");
        world.Billing.Latest = new PaymentRecord(
            "group-1", "group-1", "owner", "cs_1", "https://checkout.test/1", "pi_1",
            "price_plus", 1_200, "USD", "test", PaymentStatus.Paid,
            "https://receipt.test/1", "now", "later");

        var result = await world.Subject.GetPlusStatusAsync("group-1", TestContext.Current.CancellationToken);

        Assert.Equal(PaymentStatus.Paid, result.Status);
        Assert.Equal("https://receipt.test/1", result.ReceiptUrl);
        Assert.Equal("plus:group-1", result.EntitlementId);
    }

    [Fact]
    public void StripeGatewayVerifiesSignatureAndMapsPaidSession()
    {
        const string secret = "whsec_test_signing";
        var timestamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        var payload = $$$"""
            {
              "id":"evt_1",
              "object":"event",
              "api_version":"2025-09-30.clover",
              "created":{{{timestamp}}},
              "data":{"object":{
                "id":"cs_1",
                "object":"checkout.session",
                "amount_total":1200,
                "currency":"usd",
                "livemode":false,
                "metadata":{
                  "purchase_id":"group-1",
                  "group_id":"group-1",
                  "user_id":"owner",
                  "environment":"test",
                  "plan":"plus",
                  "price_id":"price_plus",
                  "amount_cents":"1200",
                  "currency":"USD"
                },
                "payment_intent":"pi_1",
                "payment_status":"paid"
              }},
              "livemode":false,
              "pending_webhooks":1,
              "request":{"id":"req_1","idempotency_key":"key_1"},
              "type":"checkout.session.completed"
            }
            """;
        var signed = $"{timestamp}.{payload}";
        var digest = Convert.ToHexStringLower(HMACSHA256.HashData(
            Encoding.UTF8.GetBytes(secret), Encoding.UTF8.GetBytes(signed)));
        var gateway = new StripeGateway(StripeSettings.Create(
            "test", "pk_test_x", "sk_test_x", secret, "test", "https://humbugg.test"));

        var parsed = gateway.ParseWebhook(payload, $"t={timestamp},v1={digest}");

        Assert.Equal(PaymentStatus.Paid, parsed.Status);
        Assert.Equal("group-1", parsed.PurchaseId);
        Assert.Equal("cs_1", parsed.CheckoutSessionId);
        Assert.Equal(1_200, parsed.AmountCents);
        Assert.Equal("price_plus", parsed.PriceId);
        Assert.Throws<ApiException>(() => gateway.ParseWebhook(payload, $"t={timestamp},v1=invalid"));
    }

    private static BillingWorld World(
        string userId = "owner",
        PlanCode plan = PlanCode.Free,
        string? entitlementId = null)
    {
        var groups = new FakeGroups
        {
            Group = new GroupRecord(
                "group-1", "owner", "Exchange", "", null, null, null, "USD", plan, entitlementId,
                GroupStatus.Open, "hash", [], "now", "now"),
        };
        var billing = new FakeBilling();
        var stripe = new FakeStripe();
        var settings = StripeSettings.Create(
            "test", "pk_test_x", "sk_test_x", "whsec_x", "test", "https://humbugg.test");
        var subject = new BillingService(
            new FakeUser(userId),
            groups,
            billing,
            new PlanCatalog(new PlanCatalogOptions(PlusPriceId: "price_plus")),
            stripe,
            settings);
        return new BillingWorld(subject, billing, stripe);
    }

    private sealed record BillingWorld(BillingService Subject, FakeBilling Billing, FakeStripe Stripe);

    private sealed record FakeUser(string UserId) : ICurrentUser;

    private sealed class FakeStripe : IStripeGateway
    {
        public StripeCheckoutRequest? Request { get; private set; }
        public BillingWebhookEvent? Webhook { get; set; }
        public (string Payload, string Signature)? Parsed { get; private set; }

        public Task<StripeCheckoutSession> CreateCheckoutAsync(
            StripeCheckoutRequest request,
            CancellationToken cancellationToken = default)
        {
            Request = request;
            return Task.FromResult(new StripeCheckoutSession("cs_test_1", "https://checkout.stripe.test/session"));
        }

        public BillingWebhookEvent ParseWebhook(string payload, string signature)
        {
            Parsed = (payload, signature);
            return Webhook ?? throw new InvalidOperationException("No webhook configured.");
        }
    }

    private sealed class FakeBilling : IBillingRepository
    {
        public PaymentRecord? Created { get; private set; }
        public PaymentRecord? Latest { get; set; }
        public BillingWebhookEvent? Applied { get; private set; }
        public bool ReserveResult { get; set; } = true;

        public Task<bool> ReserveAsync(PaymentRecord payment, CancellationToken cancellationToken = default)
        {
            if (ReserveResult)
            {
                Created = payment;
                Latest = payment;
            }
            return Task.FromResult(ReserveResult);
        }

        public Task AttachCheckoutAsync(
            string purchaseId,
            string checkoutSessionId,
            string checkoutUrl,
            CancellationToken cancellationToken = default)
        {
            if (Latest is not null)
                Latest = Latest with { CheckoutSessionId = checkoutSessionId, CheckoutUrl = checkoutUrl };
            return Task.CompletedTask;
        }

        public Task<PaymentRecord?> GetLatestForGroupAsync(
            string groupId,
            CancellationToken cancellationToken = default) => Task.FromResult(Latest);

        public Task<bool> ApplyEventAsync(
            BillingWebhookEvent billingEvent,
            CancellationToken cancellationToken = default)
        {
            Applied = billingEvent;
            return Task.FromResult(true);
        }
    }

    private sealed class FakeGroups : IGroupRepository
    {
        public GroupRecord? Group { get; set; }
        public Task<GroupRecord?> GetAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult(Group);
        public Task<GroupRecord> CreateAsync(GroupRecord group, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
        public Task<GroupRecord> UpdateAsync(
            string groupId,
            IReadOnlyDictionary<string, AttributeValue> fields,
            GroupStatus? expectedStatus = null,
            CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string groupId, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
        public Task CreateDrawAsync(
            string groupId,
            IReadOnlyDictionary<string, string> assignments,
            string actorUserId,
            CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<DrawRecord?> GetDrawAsync(string groupId, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
        public Task ResetDrawAsync(string groupId, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
    }
}
