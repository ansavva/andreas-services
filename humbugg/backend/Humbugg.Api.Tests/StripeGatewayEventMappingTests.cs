using Humbugg.Api.Models;
using Humbugg.Api.Services;
using System.Security.Cryptography;
using System.Text;
using Xunit;

namespace Humbugg.Api.Tests;

/// <summary>
/// <see cref="StripeGateway.ParseWebhook"/> maps every subscribed Stripe event type to a
/// <see cref="PaymentStatus"/> (see <c>docs/stripe-setup.md</c> for the subscribed set). Only
/// <c>checkout.session.completed</c> was covered before this file (in
/// <see cref="BillingServiceTests"/>) — this fills in the remaining five, each built the same
/// way: a real HMAC-SHA256 signature over the payload, so <c>EventUtility.ConstructEvent</c>
/// runs the exact verification path production traffic does.
/// </summary>
public sealed class StripeGatewayEventMappingTests
{
    private const string Secret = "whsec_test_signing";

    [Fact]
    public void AsyncPaymentSucceededMapsToPaid()
    {
        var parsed = Parse(SessionEvent(
            "checkout.session.async_payment_succeeded", "cs_1", paymentStatus: "paid"));

        Assert.Equal(PaymentStatus.Paid, parsed.Status);
        Assert.Equal("cs_1", parsed.CheckoutSessionId);
    }

    [Fact]
    public void AsyncPaymentFailedMapsToFailedRegardlessOfSessionPaymentStatus()
    {
        var parsed = Parse(SessionEvent(
            "checkout.session.async_payment_failed", "cs_2", paymentStatus: "unpaid"));

        Assert.Equal(PaymentStatus.Failed, parsed.Status);
    }

    [Fact]
    public void CheckoutSessionExpiredMapsToExpired()
    {
        var parsed = Parse(SessionEvent(
            "checkout.session.expired", "cs_3", paymentStatus: "unpaid"));

        Assert.Equal(PaymentStatus.Expired, parsed.Status);
    }

    [Fact]
    public void ChargeSucceededMapsToPaidAndCarriesTheReceiptUrl()
    {
        var parsed = Parse(ChargeEvent("charge.succeeded", refunded: false));

        Assert.Equal(PaymentStatus.Paid, parsed.Status);
        Assert.Null(parsed.CheckoutSessionId); // charge events never carry the Checkout Session id
        Assert.Equal("pi_1", parsed.PaymentIntentId);
        Assert.Equal("https://receipt.test/1", parsed.ReceiptUrl);
    }

    [Fact]
    public void FullyRefundedChargeMapsToRefunded()
    {
        var parsed = Parse(ChargeEvent("charge.refunded", refunded: true));

        Assert.Equal(PaymentStatus.Refunded, parsed.Status);
    }

    /// <summary>
    /// Stripe emits <c>charge.refunded</c> for a partial refund too (the comment on
    /// <see cref="StripeGateway"/> names this explicitly). Plus must stay active until the whole
    /// charge is refunded, so a partial refund is recorded as still-Paid, not Refunded.
    /// </summary>
    [Fact]
    public void PartiallyRefundedChargeStaysMappedAsPaid()
    {
        var parsed = Parse(ChargeEvent("charge.refunded", refunded: false));

        Assert.Equal(PaymentStatus.Paid, parsed.Status);
    }

    private static BillingWebhookEvent Parse(string payload)
    {
        var gateway = new StripeGateway(StripeSettings.Create(
            "test", "pk_test_x", "sk_test_x", Secret, "test", "https://humbugg.test"));
        var timestamp = ExtractTimestamp(payload);
        var signed = $"{timestamp}.{payload}";
        var digest = Convert.ToHexStringLower(HMACSHA256.HashData(
            Encoding.UTF8.GetBytes(Secret), Encoding.UTF8.GetBytes(signed)));
        return gateway.ParseWebhook(payload, $"t={timestamp},v1={digest}");
    }

    private static long ExtractTimestamp(string payload)
    {
        const string marker = "\"created\":";
        var start = payload.IndexOf(marker, StringComparison.Ordinal) + marker.Length;
        var end = payload.IndexOf(',', start);
        return long.Parse(payload[start..end]);
    }

    private const string Metadata = """
        "metadata":{
          "purchase_id":"group-1",
          "group_id":"group-1",
          "user_id":"owner",
          "environment":"test",
          "plan":"plus",
          "price_id":"price_plus",
          "amount_cents":"1200",
          "currency":"USD"
        }
        """;

    private static string SessionEvent(string type, string sessionId, string paymentStatus)
    {
        var timestamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        return $$$"""
            {
              "id":"evt_{{{sessionId}}}",
              "object":"event",
              "api_version":"2025-09-30.clover",
              "created":{{{timestamp}}},
              "data":{"object":{
                "id":"{{{sessionId}}}",
                "object":"checkout.session",
                "amount_total":1200,
                "currency":"usd",
                "livemode":false,
                {{{Metadata}}},
                "payment_intent":"pi_{{{sessionId}}}",
                "payment_status":"{{{paymentStatus}}}"
              }},
              "livemode":false,
              "pending_webhooks":1,
              "request":{"id":"req_1","idempotency_key":"key_1"},
              "type":"{{{type}}}"
            }
            """;
    }

    private static string ChargeEvent(string type, bool refunded)
    {
        var timestamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        var refundedLiteral = refunded ? "true" : "false";
        var eventSuffix = refunded ? "full" : "partial";
        return $$$"""
            {
              "id":"evt_charge_{{{eventSuffix}}}",
              "object":"event",
              "api_version":"2025-09-30.clover",
              "created":{{{timestamp}}},
              "data":{"object":{
                "id":"ch_1",
                "object":"charge",
                "amount":1200,
                "currency":"usd",
                "livemode":false,
                {{{Metadata}}},
                "payment_intent":"pi_1",
                "refunded":{{{refundedLiteral}}},
                "receipt_url":"https://receipt.test/1"
              }},
              "livemode":false,
              "pending_webhooks":1,
              "request":{"id":"req_1","idempotency_key":"key_1"},
              "type":"{{{type}}}"
            }
            """;
    }
}
