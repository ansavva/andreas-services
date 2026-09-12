using Amazon.Lambda.APIGatewayEvents;
using Humbugg.Api.Consumers.Realtime;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Humbugg.Api.Services.Realtime;
using System.Text.Json;
using Xunit;

namespace Humbugg.Api.Tests;

/// <summary>
/// The realtime channel (#691): what a nudge carries, and how a socket earns one.
/// </summary>
/// <remarks>
/// The anonymity rules extend to the socket. A nudge is a group and the READER's own side, never a
/// body and never a person; the ticket that opens a socket is spent on first use and dead in a
/// minute; the connection rows are keyed by user and say nothing about the draw.
/// </remarks>
public sealed class RealtimeTests
{
    private static readonly CancellationToken Token = TestContext.Current.CancellationToken;

    // ── The nudge ───────────────────────────────────────────────────────────────────────────────

    [Fact]
    public void ANudgeIsAGroupAndASideAndNothingElse()
    {
        var wire = JsonDocument.Parse(RealtimeNudge.Questions("group-1", "recipient").ToJson()).RootElement;

        Assert.Equal("questions", wire.GetProperty("type").GetString());
        Assert.Equal("group-1", wire.GetProperty("group_id").GetString());
        Assert.Equal("recipient", wire.GetProperty("side").GetString());
        Assert.Equal(3, wire.EnumerateObject().Count());
    }

    // ── Tickets ─────────────────────────────────────────────────────────────────────────────────

    [Fact]
    public async Task ATicketIsBoundToTheCallerAndSpentOnFirstUse()
    {
        var clock = new ManualClock(DateTimeOffset.Parse("2026-12-01T10:00:00Z"));
        var store = new InMemoryRealtimeConnectionStore();
        var service = new RealtimeTicketService(new FakeUser("user-ana"), store, clock);

        var issued = await service.IssueAsync(Token);

        Assert.Equal("user-ana", await store.ConsumeTicketAsync(issued.Ticket, clock.GetUtcNow(), Token));
        Assert.Null(await store.ConsumeTicketAsync(issued.Ticket, clock.GetUtcNow(), Token));
    }

    [Fact]
    public async Task ATicketDiesAfterAMinute()
    {
        var clock = new ManualClock(DateTimeOffset.Parse("2026-12-01T10:00:00Z"));
        var store = new InMemoryRealtimeConnectionStore();
        var service = new RealtimeTicketService(new FakeUser("user-ana"), store, clock);

        var issued = await service.IssueAsync(Token);
        clock.Advance(RealtimeTicketService.Lifetime + TimeSpan.FromSeconds(1));

        Assert.Null(await store.ConsumeTicketAsync(issued.Ticket, clock.GetUtcNow(), Token));
    }

    [Fact]
    public async Task TwoTicketsAreNeverTheSame()
    {
        var service = new RealtimeTicketService(new FakeUser("user-ana"), new InMemoryRealtimeConnectionStore());

        var first = await service.IssueAsync(Token);
        var second = await service.IssueAsync(Token);

        Assert.NotEqual(first.Ticket, second.Ticket);
        Assert.True(first.Ticket.Length >= 40);
        Assert.DoesNotContain('+', first.Ticket);
        Assert.DoesNotContain('/', first.Ticket);
        Assert.DoesNotContain('=', first.Ticket);
    }

    // ── The $connect authorizer ─────────────────────────────────────────────────────────────────

    [Fact]
    public async Task TheAuthorizerAllowsAValidTicketOnceAndHandsOverTheUser()
    {
        var clock = new ManualClock(DateTimeOffset.Parse("2026-12-01T10:00:00Z"));
        var store = new InMemoryRealtimeConnectionStore();
        await store.PutTicketAsync("t1", "user-bo", clock.GetUtcNow().AddSeconds(60), Token);
        var authorizer = new AwsLambdaRealtimeAuthorizer(store, clock);
        var request = new APIGatewayCustomAuthorizerRequest
        {
            MethodArn = "arn:aws:execute-api:us-east-1:1:abc/$default/$connect",
            QueryStringParameters = new Dictionary<string, string> { ["ticket"] = "t1" }
        };

        var allowed = await authorizer.AuthorizeAsync(request);
        var again = await authorizer.AuthorizeAsync(request);

        Assert.Equal("Allow", allowed.PolicyDocument.Statement.Single().Effect);
        Assert.Equal(request.MethodArn, allowed.PolicyDocument.Statement.Single().Resource.Single());
        Assert.Equal("user-bo", allowed.Context!["user_id"]);
        Assert.Equal("Deny", again.PolicyDocument.Statement.Single().Effect);
    }

    [Fact]
    public async Task TheAuthorizerDeniesAMissingTicket()
    {
        var authorizer = new AwsLambdaRealtimeAuthorizer(new InMemoryRealtimeConnectionStore(), TimeProvider.System);

        var denied = await authorizer.AuthorizeAsync(new APIGatewayCustomAuthorizerRequest
        {
            MethodArn = "arn:aws:execute-api:us-east-1:1:abc/$default/$connect"
        });

        Assert.Equal("Deny", denied.PolicyDocument.Statement.Single().Effect);
        Assert.Null(denied.Context);
    }

    // ── The route handler ───────────────────────────────────────────────────────────────────────

    [Fact]
    public async Task ConnectRecordsTheUserFromTheAuthorizerAndDisconnectForgetsIt()
    {
        var store = new InMemoryRealtimeConnectionStore();
        var handler = new AwsLambdaRealtimeConnections(store, TimeProvider.System);

        var connected = await handler.HandleAsync(Event("$connect", "c1", "user-bo"));
        Assert.Equal(200, connected.StatusCode);
        Assert.Equal(["c1"], await store.ConnectionsForUserAsync("user-bo", Token));

        Assert.Equal(200, (await handler.HandleAsync(Event("$default", "c1", null))).StatusCode);
        Assert.Equal(["c1"], await store.ConnectionsForUserAsync("user-bo", Token));

        Assert.Equal(200, (await handler.HandleAsync(Event("$disconnect", "c1", null))).StatusCode);
        Assert.Empty(await store.ConnectionsForUserAsync("user-bo", Token));
    }

    [Fact]
    public async Task ConnectWithoutAnAuthorizedUserIsRefused()
    {
        var store = new InMemoryRealtimeConnectionStore();
        var handler = new AwsLambdaRealtimeConnections(store, TimeProvider.System);

        var response = await handler.HandleAsync(Event("$connect", "c1", null));

        Assert.Equal(401, response.StatusCode);
        Assert.Empty(await store.ConnectionsForUserAsync("user-bo", Token));
    }

    private sealed class FakeUser(string userId) : ICurrentUser { public string UserId => userId; }

    /// <summary>A clock a test moves by hand.</summary>
    private sealed class ManualClock(DateTimeOffset start) : TimeProvider
    {
        private DateTimeOffset now = start;
        public override DateTimeOffset GetUtcNow() => now;
        public void Advance(TimeSpan by) => now = now.Add(by);
    }

    private static APIGatewayProxyRequest Event(string routeKey, string connectionId, string? userId)
    {
        var context = new APIGatewayProxyRequest.ProxyRequestContext { RouteKey = routeKey, ConnectionId = connectionId };
        if (userId is not null)
            context.Authorizer = new APIGatewayCustomAuthorizerContext { ["user_id"] = userId };
        return new APIGatewayProxyRequest { RequestContext = context };
    }
}
