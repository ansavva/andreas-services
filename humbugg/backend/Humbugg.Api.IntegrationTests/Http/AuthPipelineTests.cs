using System.Net;
using System.Net.Http.Headers;
using Xunit;

namespace Humbugg.Api.IntegrationTests.Http;

public sealed class AuthPipelineTests(ApiFixture api) : HttpTest(api)
{
    [IntegrationFact]
    public async Task No_token_gets_the_challenge_envelope()
    {
        using var client = Api.Client();
        var response = await client.GetAsync("/api/groups");

        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
        // OnChallenge writes a JSON body — not the framework's empty 401.
        var body = await ReadJson(response);
        Assert.Equal("unauthorized", body.GetProperty("error").GetProperty("code").GetString());
    }

    [IntegrationFact]
    public async Task An_id_token_is_not_an_access_token()
    {
        using var client = Api.Client();
        client.DefaultRequestHeaders.Authorization =
            new AuthenticationHeaderValue("Bearer", Api.MintToken(Uid("user"), tokenUse: "id"));

        var response = await client.GetAsync("/api/groups");
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    [IntegrationFact]
    public async Task A_token_for_another_app_client_is_refused()
    {
        using var client = Api.Client();
        client.DefaultRequestHeaders.Authorization =
            new AuthenticationHeaderValue("Bearer", Api.MintToken(Uid("user"), clientId: "some-other-client"));

        var response = await client.GetAsync("/api/groups");
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    [IntegrationFact]
    public async Task An_expired_token_is_refused()
    {
        using var client = Api.Client();
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue(
            "Bearer", Api.MintToken(Uid("user"), lifetime: TimeSpan.FromMinutes(-10)));

        var response = await client.GetAsync("/api/groups");
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    [IntegrationFact]
    public async Task A_valid_access_token_reaches_the_application()
    {
        using var client = Api.ClientFor(Uid("user"));
        var response = await client.GetAsync("/api/groups");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await ReadJson(response);
        Assert.Equal(System.Text.Json.JsonValueKind.Array, body.ValueKind);
    }

    [IntegrationFact]
    public async Task Health_needs_no_token()
    {
        using var client = Api.Client();
        var response = await client.GetAsync("/health");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("ok", (await ReadJson(response)).GetProperty("status").GetString());
    }
}
