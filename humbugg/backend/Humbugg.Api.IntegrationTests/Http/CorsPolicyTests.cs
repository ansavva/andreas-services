using System.Net;
using Xunit;

namespace Humbugg.Api.IntegrationTests.Http;

// CORS is load-bearing here, not decorative: the API answers on its own domain, so every
// browser request is cross-origin and ASP.NET is the single source of the Access-Control-*
// headers (API Gateway deliberately emits none). Until this suite existed, the only check
// was the post-deploy curl against production.
public sealed class CorsPolicyTests(ApiFixture api) : HttpTest(api)
{
    private static HttpRequestMessage Preflight(string origin)
    {
        var request = new HttpRequestMessage(HttpMethod.Options, "/api/groups");
        request.Headers.Add("Origin", origin);
        request.Headers.Add("Access-Control-Request-Method", "GET");
        request.Headers.Add("Access-Control-Request-Headers", "authorization");
        return request;
    }

    [IntegrationFact]
    public async Task A_configured_origin_passes_preflight()
    {
        var origin = Api.Settings.CorsOrigins[0];
        using var client = Api.Client();
        var response = await client.SendAsync(Preflight(origin));

        Assert.Equal(HttpStatusCode.NoContent, response.StatusCode);
        Assert.Equal(origin, Assert.Single(response.Headers.GetValues("Access-Control-Allow-Origin")));
        Assert.Contains("GET", response.Headers.GetValues("Access-Control-Allow-Methods").Single());
    }

    [IntegrationFact]
    public async Task An_unknown_origin_gets_no_allow_header()
    {
        using var client = Api.Client();
        var response = await client.SendAsync(Preflight("https://evil.example"));

        Assert.False(response.Headers.Contains("Access-Control-Allow-Origin"));
    }

    [IntegrationFact]
    public async Task Simple_requests_carry_the_allow_origin_header_too()
    {
        var origin = Api.Settings.CorsOrigins[0];
        using var client = Api.Client();
        var request = new HttpRequestMessage(HttpMethod.Get, "/health");
        request.Headers.Add("Origin", origin);
        var response = await client.SendAsync(request);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal(origin, Assert.Single(response.Headers.GetValues("Access-Control-Allow-Origin")));
    }
}
