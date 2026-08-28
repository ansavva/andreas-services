using System.Net;
using Xunit;

namespace Humbugg.Api.IntegrationTests.Http;

// Both halves of the error contract answer with the same {"error":{"code","message"}}
// envelope: ApiExceptionMiddleware for exceptions thrown by the application, and the
// InvalidModelStateResponseFactory for bodies the framework refuses before the
// application ever runs. The app's clients parse this shape; drift breaks them silently.
public sealed class ErrorEnvelopeTests(ApiFixture api) : HttpTest(api)
{
    [IntegrationFact]
    public async Task An_ApiException_becomes_the_error_envelope()
    {
        using var client = Api.ClientFor(Uid("user"));
        var response = await client.GetAsync($"/api/groups/{Uid("group")}");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        var error = (await ReadJson(response)).GetProperty("error");
        Assert.Equal("not_found", error.GetProperty("code").GetString());
        Assert.False(string.IsNullOrEmpty(error.GetProperty("message").GetString()));
    }

    [IntegrationFact]
    public async Task A_malformed_body_becomes_bad_request_in_the_same_envelope()
    {
        using var client = Api.ClientFor(Uid("user"));
        var response = await client.PostAsync("/api/groups", Json("{ this is not json"));

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        var error = (await ReadJson(response)).GetProperty("error");
        Assert.Equal("bad_request", error.GetProperty("code").GetString());
    }

    [IntegrationFact]
    public async Task An_unknown_route_is_a_plain_404_not_an_envelope()
    {
        // Nothing threw and nothing was bound, so neither error path runs. Pinning this stops
        // someone "helpfully" wrapping bare 404s and changing what clients see for typos.
        using var client = Api.ClientFor(Uid("user"));
        var response = await client.GetAsync("/api/definitely-not-a-route");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Empty(await response.Content.ReadAsByteArrayAsync());
    }
}
