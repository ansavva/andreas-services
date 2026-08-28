using Amazon.DynamoDBv2;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Protocols.OpenIdConnect;
using Microsoft.IdentityModel.Tokens;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using Xunit;

namespace Humbugg.Api.IntegrationTests.Http;

[CollectionDefinition("dev-stack-http")]
public sealed class ApiCollection : ICollectionFixture<ApiFixture>;

/// <summary>
/// The in-process API over the dev stack: <c>WebApplicationFactory&lt;Program&gt;</c> hosting the
/// real <c>Program.cs</c> — real routing, real CORS, real error envelopes, real repositories
/// against real dev-stack tables. Settings are environment variables read at startup, so
/// <see cref="DevEnv.Apply"/> must run before the factory is created; that is also why every
/// HTTP test shares this one fixture and collection (the environment is process-global).
///
/// Authentication is the real JwtBearer pipeline with only the key exchange replaced: a
/// symmetric test key stands in for Cognito's signing keys, and issuer validation is off
/// because the issuer is a URL derived from the pool id. Everything the app itself checks —
/// lifetime, <c>token_use</c>, <c>client_id</c>, the challenge and forbidden envelopes —
/// still executes, which is the point: those checks are the security logic under test.
/// </summary>
public sealed class ApiFixture : IAsyncLifetime
{
    private static readonly SymmetricSecurityKey SigningKey = new(RandomNumberGenerator.GetBytes(32));

    private WebApplicationFactory<Program> _factory = null!;

    public HumbuggSettings Settings { get; private set; } = null!;
    public IAmazonDynamoDB Db { get; private set; } = null!;

    public ValueTask InitializeAsync()
    {
        DevEnv.Apply();
        Settings = HumbuggSettings.FromEnvironment();
        Db = new AmazonDynamoDBClient(new AmazonDynamoDBConfig
        {
            RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(Settings.AwsRegion)
        });
        _factory = new WebApplicationFactory<Program>().WithWebHostBuilder(builder =>
            builder.ConfigureTestServices(services =>
                services.PostConfigure<JwtBearerOptions>(JwtBearerDefaults.AuthenticationScheme, options =>
                {
                    // A present (empty) configuration stops the handler fetching Cognito's
                    // OIDC metadata over the network at first validation.
                    options.Configuration = new OpenIdConnectConfiguration();
                    options.TokenValidationParameters.ValidateIssuer = false;
                    options.TokenValidationParameters.IssuerSigningKey = SigningKey;
                })));
        return ValueTask.CompletedTask;
    }

    public async ValueTask DisposeAsync()
    {
        await _factory.DisposeAsync();
        Db.Dispose();
    }

    public HttpClient Client() => _factory.CreateClient();

    /// <summary>A client that sends a valid Humbugg access token for <paramref name="sub"/>.</summary>
    public HttpClient ClientFor(string sub)
    {
        var client = _factory.CreateClient();
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", MintToken(sub));
        return client;
    }

    /// <summary>
    /// Mints a token the test pipeline accepts — or, by overriding <paramref name="tokenUse"/>,
    /// <paramref name="clientId"/>, or <paramref name="lifetime"/>, one the app must refuse.
    /// </summary>
    public string MintToken(
        string sub,
        string tokenUse = "access",
        string? clientId = null,
        TimeSpan? lifetime = null)
    {
        var now = DateTime.UtcNow;
        return new JsonWebTokenHandler().CreateToken(new SecurityTokenDescriptor
        {
            Issuer = $"https://cognito-idp.{Settings.CognitoRegion}.amazonaws.com/{Settings.CognitoUserPoolId}",
            IssuedAt = now.Add(lifetime ?? TimeSpan.Zero) - TimeSpan.FromHours(1),
            NotBefore = now.Add(lifetime ?? TimeSpan.Zero) - TimeSpan.FromHours(1),
            Expires = now.Add(lifetime ?? TimeSpan.FromHours(1)),
            SigningCredentials = new SigningCredentials(SigningKey, SecurityAlgorithms.HmacSha256),
            Claims = new Dictionary<string, object>
            {
                ["sub"] = sub,
                ["token_use"] = tokenUse,
                ["client_id"] = clientId ?? Settings.CognitoClientId
            }
        });
    }
}
