namespace Humbugg.Api.Models;

public enum PaymentStatus
{
    Pending,
    Paid,
    Failed,
    Expired,
    Refunded,
}

public sealed record CheckoutResponse(string CheckoutUrl, string SessionId, PaymentStatus Status);

public sealed record PlusPurchaseStatus(
    string GroupId,
    PaymentStatus? Status,
    string? CheckoutSessionId,
    string? CheckoutUrl,
    string? ReceiptUrl,
    string? EntitlementId,
    string? UpdatedAt);

internal sealed record PaymentRecord(
    string PurchaseId,
    string GroupId,
    string UserId,
    string CheckoutSessionId,
    string CheckoutUrl,
    string? PaymentIntentId,
    string PriceId,
    long AmountCents,
    string Currency,
    string Environment,
    PaymentStatus Status,
    string? ReceiptUrl,
    string CreatedAt,
    string UpdatedAt);

internal sealed record BillingWebhookEvent(
    string EventId,
    string PurchaseId,
    string GroupId,
    string UserId,
    string? CheckoutSessionId,
    string? PaymentIntentId,
    string PriceId,
    long AmountCents,
    string Currency,
    string Environment,
    PaymentStatus Status,
    string? ReceiptUrl,
    string EventCreatedAt);
