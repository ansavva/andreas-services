using Amazon.ApiGatewayManagementApi;
using Amazon.ApiGatewayManagementApi.Model;
using Humbugg.Api.Data;
using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;

namespace Humbugg.Api.Services.Realtime;

/// <summary>
/// A nudge: "something changed for you here, go and read it". It carries a group and a SIDE and
/// nothing else — no body, no name, no id of the other person — the same rule the email keeps
/// (#131). The client answers it with the ordinary authorized GET, which is where the content and
/// the authorization both live.
/// </summary>
public sealed record RealtimeNudge(string Type, string GroupId, string Side)
{
    public static RealtimeNudge Questions(string groupId, string side) => new("questions", groupId, side);

    internal string ToJson() => JsonSerializer.Serialize(
        new { type = Type, group_id = GroupId, side = Side });
}

/// <summary>Delivers a nudge to every socket a user currently holds. Never throws to its caller.</summary>
internal interface IRealtimeNotifier
{
    Task NudgeAsync(string userId, RealtimeNudge nudge, CancellationToken cancellationToken = default);
}

/// <summary>Production: API Gateway's management API, one PostToConnection per open socket.</summary>
internal sealed class ApiGatewayRealtimeNotifier(
    IRealtimeConnectionStore connections,
    IAmazonApiGatewayManagementApi gateway,
    ILogger<ApiGatewayRealtimeNotifier> logger) : IRealtimeNotifier
{
    public async Task NudgeAsync(string userId, RealtimeNudge nudge, CancellationToken cancellationToken = default)
    {
        IReadOnlyList<string> ids;
        try { ids = await connections.ConnectionsForUserAsync(userId, cancellationToken); }
        catch (Exception exception)
        {
            logger.LogWarning(exception, "Realtime: could not list connections");
            return;
        }
        var payload = Encoding.UTF8.GetBytes(nudge.ToJson());
        foreach (var id in ids)
        {
            try
            {
                using var body = new MemoryStream(payload);
                await gateway.PostToConnectionAsync(new PostToConnectionRequest { ConnectionId = id, Data = body }, cancellationToken);
            }
            catch (GoneException)
            {
                // The socket closed without a $disconnect reaching us. Forget it now rather than at TTL.
                try { await connections.RemoveConnectionAsync(id, cancellationToken); } catch { /* the TTL will */ }
            }
            catch (Exception exception)
            {
                logger.LogWarning(exception, "Realtime: post to connection failed");
            }
        }
    }
}

/// <summary>
/// The dev container's own sockets: Kestrel accepts the WebSocket, the hub holds it, and a nudge is
/// written straight to it. Same contract as production from the caller's side; none of the
/// infrastructure.
/// </summary>
internal sealed class InProcessRealtimeHub(IRealtimeConnectionStore connections, ILogger<InProcessRealtimeHub> logger) : IRealtimeNotifier
{
    private readonly ConcurrentDictionary<string, WebSocket> sockets = new(StringComparer.Ordinal);

    /// <summary>Holds the socket open until the client closes it, then forgets it.</summary>
    public async Task RunAsync(string userId, WebSocket socket, CancellationToken cancellationToken)
    {
        var id = Guid.NewGuid().ToString("N");
        sockets[id] = socket;
        await connections.PutConnectionAsync(id, userId, DateTimeOffset.UtcNow.AddHours(2), cancellationToken);
        logger.LogDebug("Realtime: socket held; {Held} in the hub", sockets.Count);
        var buffer = new byte[1024];
        try
        {
            while (socket.State == WebSocketState.Open)
            {
                // Anything the client sends (a ping) is read and dropped; the channel is one-way.
                var result = await socket.ReceiveAsync(buffer, cancellationToken);
                if (result.MessageType == WebSocketMessageType.Close) break;
            }
        }
        catch (OperationCanceledException) { }
        catch (WebSocketException) { }
        finally
        {
            sockets.TryRemove(id, out _);
            await connections.RemoveConnectionAsync(id, CancellationToken.None);
            if (socket.State == WebSocketState.Open || socket.State == WebSocketState.CloseReceived)
            {
                try { await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "bye", CancellationToken.None); } catch { /* gone */ }
            }
        }
    }

    public async Task NudgeAsync(string userId, RealtimeNudge nudge, CancellationToken cancellationToken = default)
    {
        var payload = Encoding.UTF8.GetBytes(nudge.ToJson());
        var ids = await connections.ConnectionsForUserAsync(userId, cancellationToken);
        // Counts only: a user id in a log line is one more place an identity could be read back from.
        logger.LogDebug("Realtime: nudging {Count} socket(s); {Held} held in the hub", ids.Count, sockets.Count);
        foreach (var id in ids)
        {
            if (!sockets.TryGetValue(id, out var socket) || socket.State != WebSocketState.Open) continue;
            try { await socket.SendAsync(payload, WebSocketMessageType.Text, true, cancellationToken); }
            catch (WebSocketException) { sockets.TryRemove(id, out _); }
        }
    }
}

/// <summary>Where the channel is switched off — a Lambda mode that never nudges, or a test.</summary>
internal sealed class NoRealtimeNotifier : IRealtimeNotifier
{
    public Task NudgeAsync(string userId, RealtimeNudge nudge, CancellationToken cancellationToken = default) => Task.CompletedTask;
}
