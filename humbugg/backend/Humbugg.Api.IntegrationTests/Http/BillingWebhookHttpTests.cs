using System.Net;
using Xunit;

namespace Humbugg.Api.IntegrationTests.Http;

// The webhook route is AllowAnonymous by necessity (Stripe is the caller, not a signed-in
// Humbugg user) — these are the two ways an unsigned or forged request must still be refused
// rather than reach BillingService.ProcessWebhookAsync.
public sealed class BillingWebhookHttpTests(ApiFixture api) : HttpTest(api)
{
    [IntegrationFact]
    public async Task A_request_with_no_Stripe_Signature_header_is_refused()
    {
        using var client = Api.Client();

        var response = await client.PostAsync("/api/billing/stripe/webhook", Json("{}"));

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        var error = (await ReadJson(response)).GetProperty("error");
        Assert.Equal("bad_request", error.GetProperty("code").GetString());
    }

    [IntegrationFact]
    public async Task A_request_with_an_invalid_signature_is_refused_before_any_Stripe_parsing()
    {
        using var client = Api.Client();
        var request = new HttpRequestMessage(HttpMethod.Post, "/api/billing/stripe/webhook")
        {
            Content = Json("""{"id": "evt_forged", "type": "checkout.session.completed"}"""),
        };
        request.Headers.Add("Stripe-Signature", "t=1,v1=0000000000000000000000000000000000000000000000000000000000000000");

        var response = await client.SendAsync(request);

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        var error = (await ReadJson(response)).GetProperty("error");
        Assert.Equal("bad_request", error.GetProperty("code").GetString());
        Assert.Contains("Invalid Stripe webhook", error.GetProperty("message").GetString());
    }
}
