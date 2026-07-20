using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Humbugg.Api.Controllers;

[ApiController, Authorize, Route("api/groups/{groupId}/billing/plus")]
public sealed class BillingController(IBillingService billing) : ControllerBase
{
    [HttpPost("checkout")]
    public Task<CheckoutResponse> Checkout(string groupId, CancellationToken cancellationToken) =>
        billing.CreatePlusCheckoutAsync(groupId, cancellationToken);

    [HttpGet]
    public Task<PlusPurchaseStatus> Status(string groupId, CancellationToken cancellationToken) =>
        billing.GetPlusStatusAsync(groupId, cancellationToken);
}

[ApiController, AllowAnonymous, Route("api/billing/stripe")]
public sealed class StripeWebhookController(IBillingService billing) : ControllerBase
{
    [HttpPost("webhook")]
    public async Task<IActionResult> Webhook(CancellationToken cancellationToken)
    {
        using var reader = new StreamReader(Request.Body);
        var payload = await reader.ReadToEndAsync(cancellationToken);
        if (!Request.Headers.TryGetValue("Stripe-Signature", out var signature) ||
            string.IsNullOrWhiteSpace(signature))
            throw ApiException.BadRequest("Stripe-Signature is required.");
        await billing.ProcessWebhookAsync(payload, signature.ToString(), cancellationToken);
        return Ok(new { received = true });
    }
}
