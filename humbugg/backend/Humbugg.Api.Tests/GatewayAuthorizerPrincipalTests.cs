using Microsoft.Extensions.DependencyInjection;
using System.Net;
using System.Text.Json;
using Xunit;

namespace Humbugg.Api.Tests;

/// <summary>
/// The application decides who is authenticated, not the host in front of it (#656).
/// </summary>
/// <remarks>
/// <para>
/// Production disagreed with every other tier for months and nothing caught it. An ID token was
/// refused locally, refused by the integration suite, and accepted by <c>api.humbugg.com</c>, because
/// two layers combined: API Gateway's JWT authorizer takes an ID token (its <c>aud</c> is the app
/// client) and <c>Amazon.Lambda.AspNetCoreServer</c> then writes the authorizer's claims onto
/// <c>HttpContext.User</c> before ASP.NET sees the request. <c>UseAuthentication</c> does not clear a
/// principal it did not set, so a failed <c>OnTokenValidated</c> left the host's principal standing
/// and <c>[Authorize]</c> was satisfied by it.
/// </para>
/// <para>
/// Every test here therefore sends both halves of what API Gateway sends — the bearer token and the
/// authorizer's claim map — and the claim map is turned into a principal by the hosting package's own
/// marshaller (see <see cref="GatewayAuthorizer"/>), not by an imitation of it.
/// </para>
/// </remarks>
[Collection("hosted-api")]
public sealed class GatewayAuthorizerPrincipalTests(HostedApiFixture api)
{
    private const string Subject = "11111111-2222-3333-4444-555555555555";

    /// <summary>The claim map API Gateway hands the Lambda for a Cognito ID token.</summary>
    private static Dictionary<string, string> IdTokenClaims() => new()
    {
        ["sub"] = Subject,
        ["token_use"] = "id",
        ["aud"] = HostedApiEnvironment.ClientId,
        ["cognito:username"] = Subject,
        ["email_verified"] = "true"
    };

    /// <summary>The same, for an access token — <c>client_id</c> where the ID token had <c>aud</c>.</summary>
    private static Dictionary<string, string> AccessTokenClaims() => new()
    {
        ["sub"] = Subject,
        ["token_use"] = "access",
        ["client_id"] = HostedApiEnvironment.ClientId,
        ["scope"] = "aws.cognito.signin.user.admin"
    };

    /// <summary>
    /// The finding itself: an ID token that cleared the gateway is still refused by the application.
    /// </summary>
    /// <remarks>
    /// This is the test that fails on the commit before the fix, where it gets <c>200</c> — the
    /// gateway's principal carried the same <c>sub</c>, so the request ran as that user.
    /// </remarks>
    [Fact]
    public async Task An_id_token_is_refused_even_when_the_gateway_let_it_through()
    {
        using var client = api.BehindTheGateway(
            HostedApiFixture.MintToken(Subject, tokenUse: "id"), IdTokenClaims());

        var response = await client.GetAsync("/api/me", TestContext.Current.CancellationToken);

        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
        var body = await ReadJson(response);
        Assert.Equal("unauthorized", body.GetProperty("error").GetProperty("code").GetString());
    }

    /// <summary>
    /// A token minted for another app client, likewise — the second half of the
    /// <c>OnTokenValidated</c> rule, which the same bypass disarmed.
    /// </summary>
    [Fact]
    public async Task A_token_for_another_app_client_is_refused_behind_the_gateway()
    {
        var claims = AccessTokenClaims();
        claims["client_id"] = "some-other-client";

        using var client = api.BehindTheGateway(
            HostedApiFixture.MintToken(Subject, clientId: "some-other-client"), claims);

        var response = await client.GetAsync("/api/me", TestContext.Current.CancellationToken);

        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    /// <summary>
    /// A bearer header the application cannot validate at all does not fall back to the gateway's
    /// principal either. The gateway would not have passed this, but the application must not be
    /// relying on that.
    /// </summary>
    [Fact]
    public async Task A_garbage_token_does_not_fall_back_to_the_authorizer_claims()
    {
        using var client = api.BehindTheGateway("not.a.jwt", AccessTokenClaims());

        var response = await client.GetAsync("/api/me", TestContext.Current.CancellationToken);

        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    /// <summary>The other direction: a real access token still works, and still names its subject.</summary>
    [Fact]
    public async Task An_access_token_reaches_the_application_behind_the_gateway()
    {
        using var client = api.BehindTheGateway(
            HostedApiFixture.MintToken(Subject), AccessTokenClaims());

        var response = await client.GetAsync("/api/me", TestContext.Current.CancellationToken);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await ReadJson(response);
        Assert.Equal(Subject, body.GetProperty("user_id").GetString());
    }

    /// <summary>
    /// An anonymous route stays anonymous. Naming a scheme on the default policy makes the
    /// authorization middleware authenticate on endpoints that carry <c>[Authorize]</c> anywhere in
    /// their metadata — <c>[AllowAnonymous]</c> actions on an <c>[Authorize]</c> controller included —
    /// so this pins that they still answer without a token. <see cref="AnonymousSurfaceTests"/> pins
    /// which routes those are.
    /// </summary>
    [Fact]
    public async Task An_anonymous_route_still_answers_without_a_token()
    {
        using var client = api.Direct();

        var response = await client.GetAsync("/api/plans", TestContext.Current.CancellationToken);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    /// <summary>Health carries no authorization metadata at all, which is why no fallback policy is set.</summary>
    [Fact]
    public async Task Health_still_answers_without_a_token()
    {
        using var client = api.Direct();

        var response = await client.GetAsync("/health", TestContext.Current.CancellationToken);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    /// <summary>
    /// What the hosting package actually does, asserted directly rather than described in a comment:
    /// the authorizer's claims become an authenticated identity, which is the reason
    /// <c>[Authorize]</c> was satisfied without the application validating anything.
    /// </summary>
    [Fact]
    public void The_lambda_host_turns_authorizer_claims_into_an_authenticated_principal()
    {
        var services = new ServiceCollection().AddLogging().BuildServiceProvider();

        var principal = GatewayAuthorizer.PrincipalFor(IdTokenClaims(), services);

        Assert.NotNull(principal);
        Assert.True(principal.Identity!.IsAuthenticated);
        Assert.Equal("AuthorizerIdentity", principal.Identity.AuthenticationType);
        Assert.Equal(Subject, principal.FindFirst("sub")?.Value);
        Assert.Equal("id", principal.FindFirst("token_use")?.Value);
    }

    private static async Task<JsonElement> ReadJson(HttpResponseMessage response)
    {
        var body = await response.Content.ReadAsStringAsync(TestContext.Current.CancellationToken);
        return JsonDocument.Parse(body).RootElement.Clone();
    }
}
