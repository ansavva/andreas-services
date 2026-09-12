using Amazon.DynamoDBv2;
using Amazon.Lambda.APIGatewayEvents;
using Amazon.Lambda.RuntimeSupport;
using Amazon.Lambda.Serialization.SystemTextJson;
using Humbugg.Api.Data;

namespace Humbugg.Api.Consumers.Realtime;

/// <summary>
/// The WebSocket API's <c>$connect</c> authorizer (#691): spends the ticket in the query string and
/// hands the user id it was minted for to the connection handler through the authorizer context.
/// </summary>
/// <remarks>
/// A REQUEST authorizer is the only kind a WebSocket API can have, and <c>$connect</c> is the only
/// route it can guard. The ticket is deleted as it is read, so a second connect with the same value
/// is refused; an expired one is refused by the same conditional write. The policy allows exactly
/// the one route that was asked for.
/// </remarks>
internal sealed class AwsLambdaRealtimeAuthorizer(IRealtimeConnectionStore store, TimeProvider clock)
{
    public const string ConsumerName = "realtime-authorizer";
    internal const string TicketParameter = "ticket";
    internal const string UserIdContextKey = "user_id";

    public async Task<APIGatewayCustomAuthorizerResponse> AuthorizeAsync(APIGatewayCustomAuthorizerRequest request)
    {
        var ticket = request.QueryStringParameters is not null &&
            request.QueryStringParameters.TryGetValue(TicketParameter, out var value) ? value : null;
        var userId = string.IsNullOrWhiteSpace(ticket)
            ? null
            : await store.ConsumeTicketAsync(ticket, clock.GetUtcNow());
        return userId is null ? Deny(request.MethodArn) : Allow(request.MethodArn, userId);
    }

    internal static APIGatewayCustomAuthorizerResponse Allow(string methodArn, string userId) => new()
    {
        PrincipalID = userId,
        PolicyDocument = Policy("Allow", methodArn),
        Context = new APIGatewayCustomAuthorizerContextOutput { [UserIdContextKey] = userId }
    };

    internal static APIGatewayCustomAuthorizerResponse Deny(string methodArn) => new()
    {
        PrincipalID = "anonymous",
        PolicyDocument = Policy("Deny", methodArn)
    };

    private static APIGatewayCustomAuthorizerPolicy Policy(string effect, string resource) => new()
    {
        Version = "2012-10-17",
        Statement =
        [
            new APIGatewayCustomAuthorizerPolicy.IAMPolicyStatement
            {
                Effect = effect,
                Action = ["execute-api:Invoke"],
                Resource = [resource]
            }
        ]
    };

    public static async Task RunAsync()
    {
        var settings = RealtimeConsumerSettings.FromEnvironment();
        using var db = new AmazonDynamoDBClient(Amazon.RegionEndpoint.GetBySystemName(settings.AwsRegion));
        var authorizer = new AwsLambdaRealtimeAuthorizer(
            new DynamoDbRealtimeConnectionStore(db, settings.ConnectionsTable), TimeProvider.System);
        using var bootstrap = LambdaBootstrapBuilder
            .Create<APIGatewayCustomAuthorizerRequest, APIGatewayCustomAuthorizerResponse>(
                authorizer.AuthorizeAsync, new DefaultLambdaJsonSerializer())
            .Build();
        await bootstrap.RunAsync();
    }
}

/// <summary>Exactly what the two realtime Lambdas read: the region and the connections table.</summary>
internal sealed record RealtimeConsumerSettings(string AwsRegion, string ConnectionsTable)
{
    public static RealtimeConsumerSettings FromEnvironment()
    {
        var table = Environment.GetEnvironmentVariable("HUMBUGG_CHAT_CONNECTIONS_TABLE");
        if (string.IsNullOrWhiteSpace(table))
            throw new InvalidOperationException("HUMBUGG_CHAT_CONNECTIONS_TABLE is required for the realtime consumers.");
        return new(
            Environment.GetEnvironmentVariable("AWS_REGION") ?? Environment.GetEnvironmentVariable("AWS_DEFAULT_REGION") ?? "us-east-1",
            table);
    }
}
