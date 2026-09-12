using Humbugg.Api.Data;
using System.Security.Cryptography;

namespace Humbugg.Api.Services.Realtime;

public sealed record RealtimeTicket(string Ticket, string ExpiresAt);

public interface IRealtimeTicketService
{
    /// <summary>A one-time ticket for the caller, good for sixty seconds.</summary>
    Task<RealtimeTicket> IssueAsync(CancellationToken cancellationToken = default);
}

/// <summary>
/// The ticket is the only credential that ever appears in the socket URL. It is 256 random bits,
/// bound to the user who asked for it, spent on first use, and dead after a minute — so a value that
/// lands in an access log opens nothing. The access token stays in the Authorization header of the
/// request that minted it.
/// </summary>
internal sealed class RealtimeTicketService(
    ICurrentUser user,
    IRealtimeConnectionStore connections,
    TimeProvider? timeProvider = null) : IRealtimeTicketService
{
    internal static readonly TimeSpan Lifetime = TimeSpan.FromSeconds(60);
    private readonly TimeProvider clock = timeProvider ?? TimeProvider.System;

    public async Task<RealtimeTicket> IssueAsync(CancellationToken cancellationToken = default)
    {
        var ticket = Base64Url(RandomNumberGenerator.GetBytes(32));
        var expiresAt = clock.GetUtcNow().Add(Lifetime);
        await connections.PutTicketAsync(ticket, user.UserId, expiresAt, cancellationToken);
        return new RealtimeTicket(ticket, expiresAt.ToString("O"));
    }

    private static string Base64Url(byte[] bytes) =>
        Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');
}
