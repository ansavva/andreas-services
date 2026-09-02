using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Stripe;
using Stripe.Checkout;

namespace Humbugg.Api.Services;

internal interface IStripeGateway
{
    Task<StripeCheckoutSession> CreateCheckoutAsync(
        StripeCheckoutRequest request,
        CancellationToken cancellationToken = default);
    BillingWebhookEvent ParseWebhook(string payload, string signature);
}

internal sealed record StripeCheckoutRequest(
    string PurchaseId,
    string GroupId,
    string UserId,
    string PriceId,
    long AmountCents,
    string Currency,
    string SuccessUrl,
    string CancelUrl);

internal sealed record StripeCheckoutSession(string Id, string Url);

internal sealed class StripeGateway(StripeSettings settings) : IStripeGateway
{
    public async Task<StripeCheckoutSession> CreateCheckoutAsync(
        StripeCheckoutRequest request,
        CancellationToken cancellationToken = default)
    {
        EnsureEnabled();
        var client = new StripeClient(settings.SecretKey);
        var service = new SessionService(client);
        var metadata = new Dictionary<string, string>
        {
            ["purchase_id"] = request.PurchaseId,
            ["group_id"] = request.GroupId,
            ["user_id"] = request.UserId,
            ["environment"] = settings.Environment,
            ["plan"] = "plus",
            ["price_id"] = request.PriceId,
            ["amount_cents"] = request.AmountCents.ToString(System.Globalization.CultureInfo.InvariantCulture),
            ["currency"] = request.Currency,
        };
        var session = await service.CreateAsync(new SessionCreateOptions
        {
            Mode = "payment",
            SuccessUrl = request.SuccessUrl,
            CancelUrl = request.CancelUrl,
            ClientReferenceId = request.GroupId,
            LineItems = [new SessionLineItemOptions { Price = request.PriceId, Quantity = 1 }],
            Metadata = metadata,
            PaymentIntentData = new SessionPaymentIntentDataOptions { Metadata = metadata },
        }, new RequestOptions { IdempotencyKey = $"humbugg-plus-{request.PurchaseId}" }, cancellationToken);
        return new StripeCheckoutSession(session.Id, session.Url);
    }

    public BillingWebhookEvent ParseWebhook(string payload, string signature)
    {
        EnsureEnabled();
        Event stripeEvent;
        try
        {
            stripeEvent = EventUtility.ConstructEvent(
                payload, signature, settings.WebhookSecret, throwOnApiVersionMismatch: false);
        }
        catch (StripeException exception)
        {
            throw ApiException.BadRequest($"Invalid Stripe webhook: {exception.Message}");
        }
        if (stripeEvent.Livemode)
            throw ApiException.BadRequest("Live-mode Stripe events are not accepted.");

        return stripeEvent.Type switch
        {
            EventTypes.CheckoutSessionCompleted or EventTypes.CheckoutSessionAsyncPaymentSucceeded =>
                FromSession(stripeEvent, PaymentStatus.Paid),
            EventTypes.CheckoutSessionAsyncPaymentFailed =>
                FromSession(stripeEvent, PaymentStatus.Failed),
            EventTypes.CheckoutSessionExpired =>
                FromSession(stripeEvent, PaymentStatus.Expired),
            EventTypes.ChargeSucceeded =>
                FromCharge(stripeEvent, PaymentStatus.Paid),
            EventTypes.ChargeRefunded =>
                FromCharge(stripeEvent, PaymentStatus.Refunded),
            _ => throw new UnsupportedStripeEventException(),
        };
    }

    private BillingWebhookEvent FromSession(Event stripeEvent, PaymentStatus requestedStatus)
    {
        var session = stripeEvent.Data.Object as Session
            ?? throw ApiException.BadRequest("Stripe event did not contain a Checkout Session.");
        var status = requestedStatus == PaymentStatus.Paid && session.PaymentStatus != "paid"
            ? PaymentStatus.Pending
            : requestedStatus;
        return FromMetadata(
            stripeEvent, session.Metadata, session.Id, session.PaymentIntentId,
            session.AmountTotal ?? 0, session.Currency, status, null);
    }

    private BillingWebhookEvent FromCharge(Event stripeEvent, PaymentStatus requestedStatus)
    {
        var charge = stripeEvent.Data.Object as Charge
            ?? throw ApiException.BadRequest("Stripe event did not contain a charge.");
        // charge.refunded is emitted for partial refunds too. Plus remains active until Stripe
        // marks the entire charge refunded; partial refunds still update the receipt/status row.
        var status = requestedStatus == PaymentStatus.Refunded && !charge.Refunded
            ? PaymentStatus.Paid
            : requestedStatus;
        return FromMetadata(
            stripeEvent, charge.Metadata, null, charge.PaymentIntentId,
            charge.Amount, charge.Currency, status, charge.ReceiptUrl);
    }

    private BillingWebhookEvent FromMetadata(
        Event stripeEvent,
        IReadOnlyDictionary<string, string> metadata,
        string? sessionId,
        string? paymentIntentId,
        long amountCents,
        string currency,
        PaymentStatus status,
        string? receiptUrl)
    {
        static string Required(IReadOnlyDictionary<string, string> values, string key) =>
            values.TryGetValue(key, out var value) && !string.IsNullOrWhiteSpace(value)
                ? value
                : throw ApiException.BadRequest($"Stripe event metadata is missing '{key}'.");
        var environment = Required(metadata, "environment");
        if (Required(metadata, "plan") != "plus" || environment != settings.Environment)
            throw ApiException.BadRequest("Stripe event metadata targets the wrong plan or environment.");
        var configuredAmount = long.TryParse(
            Required(metadata, "amount_cents"),
            System.Globalization.NumberStyles.None,
            System.Globalization.CultureInfo.InvariantCulture,
            out var parsedAmount)
            ? parsedAmount
            : throw ApiException.BadRequest("Stripe event metadata contains an invalid amount.");
        var configuredCurrency = Required(metadata, "currency").ToUpperInvariant();
        if (configuredAmount != amountCents ||
            !configuredCurrency.Equals(currency, StringComparison.OrdinalIgnoreCase))
            throw ApiException.BadRequest("Stripe event amount or currency does not match Checkout.");
        return new BillingWebhookEvent(
            stripeEvent.Id,
            Required(metadata, "purchase_id"),
            Required(metadata, "group_id"),
            Required(metadata, "user_id"),
            sessionId,
            paymentIntentId,
            Required(metadata, "price_id"),
            configuredAmount,
            configuredCurrency,
            environment,
            status,
            receiptUrl,
            stripeEvent.Created.ToUniversalTime().ToString("O"));
    }

    private void EnsureEnabled()
    {
        if (!settings.IsEnabled)
            throw ApiException.Conflict("Plus purchasing is temporarily unavailable.");
    }
}

internal sealed class UnsupportedStripeEventException : Exception;

public interface IBillingService
{
    Task<CheckoutResponse> CreatePlusCheckoutAsync(string groupId, CancellationToken cancellationToken = default);
    Task<PlusPurchaseStatus> GetPlusStatusAsync(string groupId, CancellationToken cancellationToken = default);
    Task ProcessWebhookAsync(string payload, string signature, CancellationToken cancellationToken = default);
}

internal sealed class BillingService(
    ICurrentUser user,
    IGroupRepository groups,
    IBillingRepository billing,
    IPlanCatalog plans,
    IStripeGateway stripe,
    StripeSettings settings) : IBillingService
{
    public async Task<CheckoutResponse> CreatePlusCheckoutAsync(
        string groupId,
        CancellationToken cancellationToken = default)
    {
        if (!settings.IsEnabled) throw ApiException.Conflict("Plus purchasing is temporarily unavailable.");
        var group = await RequireOwnerAsync(groupId, cancellationToken);
        if (group.Plan == PlanCode.Plus && group.EntitlementId is not null)
            throw ApiException.Conflict("This exchange already has Plus.");
        if (group.Plan != PlanCode.Free)
            throw ApiException.Conflict("Only Free exchanges can be upgraded to Plus.");

        var plan = plans.Get(PlanCode.Plus);
        if (string.IsNullOrWhiteSpace(plan.PriceId))
            throw ApiException.Conflict("Plus purchasing is not configured.");

        var purchaseId = Guid.NewGuid().ToString("N");
        var now = DateTimeOffset.UtcNow.ToString("O");
        var reserved = new Humbugg.Api.Models.PaymentRecord(
            purchaseId, groupId, user.UserId, "", "", null, plan.PriceId, plan.PriceCents,
            plan.Currency, settings.Environment, PaymentStatus.Pending, null, now, now);
        if (!await billing.ReserveAsync(reserved, cancellationToken))
        {
            var existing = await billing.GetLatestForGroupAsync(groupId, cancellationToken);
            if (existing?.Status != PaymentStatus.Pending)
                throw ApiException.Conflict("A Plus purchase is already being prepared for this exchange.");
            if (!string.IsNullOrWhiteSpace(existing.CheckoutUrl))
                return new CheckoutResponse(existing.CheckoutUrl, existing.CheckoutSessionId, existing.Status);
            // The Lambda may have stopped after Stripe accepted the request but before the Session
            // was attached. Reuse the same purchase/idempotency key so Stripe returns that Session
            // instead of opening a second payable Checkout.
            purchaseId = existing.PurchaseId;
        }

        // The organizer's billing area, on the product app's own origin. NOT `/app/groups/...`:
        // that shape is from when the app was served under www.humbugg.com/app, and only the
        // marketing origin still 301s it. APP_BASE_URL is app.humbugg.com, which never did, so a
        // paid return landed on the not-found screen with the purchase invisible.
        var returnBase = $"{settings.ReturnBaseUrl}/organize/{Uri.EscapeDataString(groupId)}";
        StripeCheckoutSession session;
        session = await stripe.CreateCheckoutAsync(new StripeCheckoutRequest(
            purchaseId,
            groupId,
            user.UserId,
            plan.PriceId,
            plan.PriceCents,
            plan.Currency,
            $"{returnBase}?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
            $"{returnBase}?checkout=canceled"), cancellationToken);
        await billing.AttachCheckoutAsync(purchaseId, session.Id, session.Url, cancellationToken);
        return new CheckoutResponse(session.Url, session.Id, PaymentStatus.Pending);
    }

    public async Task<PlusPurchaseStatus> GetPlusStatusAsync(
        string groupId,
        CancellationToken cancellationToken = default)
    {
        var group = await RequireOwnerAsync(groupId, cancellationToken);
        var payment = await billing.GetLatestForGroupAsync(groupId, cancellationToken);
        return new PlusPurchaseStatus(
            groupId,
            payment?.Status,
            payment?.CheckoutSessionId,
            payment?.CheckoutUrl,
            payment?.ReceiptUrl,
            group.EntitlementId,
            payment?.UpdatedAt);
    }

    public async Task ProcessWebhookAsync(
        string payload,
        string signature,
        CancellationToken cancellationToken = default)
    {
        BillingWebhookEvent billingEvent;
        try { billingEvent = stripe.ParseWebhook(payload, signature); }
        catch (UnsupportedStripeEventException) { return; }
        await billing.ApplyEventAsync(billingEvent, cancellationToken);
    }

    private async Task<GroupRecord> RequireOwnerAsync(string groupId, CancellationToken cancellationToken)
    {
        var group = await groups.GetAsync(groupId, cancellationToken)
            ?? throw ApiException.NotFound("Exchange not found.");
        if (group.OwnerUserId != user.UserId)
            throw ApiException.Forbidden("Only the exchange owner can manage billing.");
        return group;
    }
}
