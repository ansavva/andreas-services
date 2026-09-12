using Amazon.DynamoDBv2;
using Amazon.Lambda.APIGatewayEvents;
using Amazon.Lambda.RuntimeSupport;
using Amazon.Lambda.Serialization.SystemTextJson;
using Humbugg.Api.Data;

namespace Humbugg.Api.Consumers.Realtime;

/// <summary>
/// The WebSocket API's route handler (#691): records a connection on <c>$connect</c>, forgets it on
/// <c>$disconnect</c>, and ignores anything a client sends — the channel is one-way, and a message
/// from a client is a ping to keep API Gateway's idle timer from closing it.
/// </summary>
/// <remarks>
/// The user id comes from the authorizer's context, never from the client. A connection row lives
/// two hours at most: API Gateway closes a socket at two hours regardless, and the TTL makes a
/// missed <c>$disconnect</c> a stale row rather than a leak. A nudge to a gone connection is also
/// how the notifier learns to delete one early.
/// </remarks>
internal sealed class AwsLambdaRealtimeConnections(IRealtimeConnectionStore store, TimeProvider clock)
{
    public const string ConsumerName = "realtime-connections";
    internal static readonly TimeSpan ConnectionLifetime = TimeSpan.FromHours(2);

    public async Task<APIGatewayProxyResponse> HandleAsync(APIGatewayProxyRequest request)
    {
        var context = request.RequestContext;
        var connectionId = context?.ConnectionId;
        if (string.IsNullOrWhiteSpace(connectionId)) return new APIGatewayProxyResponse { StatusCode = 400 };

        switch (context!.RouteKey)
        {
            case "$connect":
                var userId = UserId(context);
                if (userId is null) return new APIGatewayProxyResponse { StatusCode = 401 };
                await store.PutConnectionAsync(connectionId, userId, clock.GetUtcNow().Add(ConnectionLifetime));
                break;
            case "$disconnect":
                await store.RemoveConnectionAsync(connectionId);
                break;
            default:
                break;
        }
        return new APIGatewayProxyResponse { StatusCode = 200 };
    }

    private static string? UserId(APIGatewayProxyRequest.ProxyRequestContext context)
    {
        if (context.Authorizer is null) return null;
        return context.Authorizer.TryGetValue(AwsLambdaRealtimeAuthorizer.UserIdContextKey, out var value) &&
            value is string userId && !string.IsNullOrWhiteSpace(userId)
            ? userId
            : null;
    }

    public static async Task RunAsync()
    {
        var settings = RealtimeConsumerSettings.FromEnvironment();
        using var db = new AmazonDynamoDBClient(Amazon.RegionEndpoint.GetBySystemName(settings.AwsRegion));
        var handler = new AwsLambdaRealtimeConnections(
            new DynamoDbRealtimeConnectionStore(db, settings.ConnectionsTable), TimeProvider.System);
        using var bootstrap = LambdaBootstrapBuilder
            .Create<APIGatewayProxyRequest, APIGatewayProxyResponse>(handler.HandleAsync, new DefaultLambdaJsonSerializer())
            .Build();
        await bootstrap.RunAsync();
    }
}
