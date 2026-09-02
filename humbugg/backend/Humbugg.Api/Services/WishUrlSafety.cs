using System.Net;
using System.Net.Sockets;

namespace Humbugg.Api.Services;

/// <summary>
/// Whether Humbugg's servers are willing to make a request to a URL somebody pasted (#129).
/// </summary>
/// <remarks>
/// <para>
/// This is the whole security surface of wishlist link previews. Everything else in that feature is
/// parsing; this is the part that decides whether a participant can point the API at
/// <c>http://169.254.169.254/latest/meta-data/iam/security-credentials/</c> and have it fetched with
/// the Lambda's own network position.
/// </para>
/// <para>
/// **The check is on the resolved ADDRESS, never on the name.** A hostname is attacker-controlled
/// input that resolves to whatever its owner's DNS says today, so <c>example.com</c> and
/// <c>localhost.evil.test</c> are the same kind of thing — a string that becomes an IP later. Only
/// the IP can be judged.
/// </para>
/// <para>
/// **And the connection is made to the address that was checked.** Validating a name and then
/// handing it to a socket to resolve again is a DNS-rebinding hole: the second lookup can answer
/// differently from the first. <see cref="ConnectAsync"/> resolves once, judges every answer, and
/// dials the one it approved. That is why this class owns the connect callback rather than exposing
/// a `bool IsAllowed(string)` somebody would call before an ordinary `HttpClient.GetAsync`.
/// </para>
/// </remarks>
internal static class WishUrlSafety
{
    /// <summary>The only ports worth reaching for a product page, and a poor port-scanner.</summary>
    private static readonly int[] AllowedPorts = [80, 443];

    /// <summary>
    /// Why a URL was refused before any packet was sent.
    /// </summary>
    /// <remarks>
    /// Only reasons decidable from the URL ITSELF appear here. A refusal that needed DNS or a
    /// connection is deliberately not distinguishable from a timeout — see the service — because the
    /// difference between "blocked, it is internal" and "did not answer" is a port scanner.
    /// </remarks>
    public enum Refusal
    {
        None,
        NotAbsoluteHttp,
        HasCredentials,
        UnusualPort,
        LiteralPrivateAddress,
    }

    /// <summary>Checks what the URL says about itself. Nothing here touches the network.</summary>
    public static Refusal Inspect(Uri uri)
    {
        if (!uri.IsAbsoluteUri || (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps))
            return Refusal.NotAbsoluteHttp;
        // `http://user:pass@host` — credentials that would be sent to a third party, and a common
        // way to make a hostile URL read like a familiar one in a link preview.
        if (!string.IsNullOrEmpty(uri.UserInfo)) return Refusal.HasCredentials;
        if (!AllowedPorts.Contains(uri.Port)) return Refusal.UnusualPort;
        // A literal address can be judged now, which gives a clearer message than a silent failure.
        // A hostname cannot be judged at all until it is resolved.
        if (IPAddress.TryParse(uri.Host.Trim('[', ']'), out var literal) && !IsPublic(literal))
            return Refusal.LiteralPrivateAddress;
        return Refusal.None;
    }

    /// <summary>
    /// Whether an address is somewhere on the public internet, as opposed to somewhere inside.
    /// </summary>
    /// <remarks>
    /// Written as an allowlist of "not any of these", because the failure mode of forgetting a range
    /// is that it becomes reachable. The one that matters most is 169.254.0.0/16: it holds the
    /// cloud instance-metadata service, which on an unprotected instance hands out role credentials
    /// to anything that can make an HTTP request from it.
    /// </remarks>
    public static bool IsPublic(IPAddress address)
    {
        // ::ffff:127.0.0.1 is loopback wearing an IPv6 costume, and every check below would miss it.
        if (address.IsIPv4MappedToIPv6) address = address.MapToIPv4();

        if (IPAddress.IsLoopback(address)) return false;

        if (address.AddressFamily == AddressFamily.InterNetwork)
        {
            var octets = address.GetAddressBytes();
            return octets[0] switch
            {
                0 => false,                                  // "this network", and 0.0.0.0
                10 => false,                                 // private
                127 => false,                                // loopback, belt and braces
                100 => octets[1] is < 64 or > 127,           // 100.64/10 carrier-grade NAT
                169 => octets[1] != 254,                     // 169.254/16 link-local AND metadata
                172 => octets[1] is < 16 or > 31,            // 172.16/12 private
                192 => !(octets[1] == 168 || (octets[1] == 0 && octets[2] == 0)), // 192.168/16, 192.0.0/24
                198 => !(octets[1] is 18 or 19),             // 198.18/15 benchmarking
                >= 224 => false,                             // multicast and reserved, incl. broadcast
                _ => true,
            };
        }

        if (address.AddressFamily == AddressFamily.InterNetworkV6)
        {
            if (address.IsIPv6LinkLocal || address.IsIPv6SiteLocal || address.IsIPv6Multicast) return false;
            if (address.Equals(IPAddress.IPv6Any) || address.Equals(IPAddress.IPv6None)) return false;
            // fc00::/7 unique-local, the IPv6 equivalent of 10/8.
            if ((address.GetAddressBytes()[0] & 0xFE) == 0xFC) return false;
            return true;
        }

        // Anything that is not IPv4 or IPv6 is not something to be dialling.
        return false;
    }

    /// <summary>
    /// Resolves a host, refuses every non-public answer, and connects to one that survived.
    /// </summary>
    /// <remarks>
    /// Installed as <c>SocketsHttpHandler.ConnectCallback</c>, so it runs for the initial request and
    /// for anything the stack dials afterwards. Resolving here rather than in a caller is what closes
    /// the gap between "checked" and "connected" — with a separate pre-check, DNS is free to answer
    /// <c>93.184.216.34</c> to the validator and <c>169.254.169.254</c> to the socket a millisecond
    /// later.
    ///
    /// ALL answers must be public, not merely one: accepting a host that resolves to both a public
    /// and a private address would let an attacker pin the private one by ordering or by racing.
    /// </remarks>
    public static async ValueTask<Stream> ConnectAsync(
        DnsEndPoint endPoint,
        CancellationToken cancellationToken)
    {
        var addresses = await Dns.GetHostAddressesAsync(endPoint.Host, cancellationToken);
        if (addresses.Length == 0) throw new HttpRequestException("The address could not be resolved.");
        if (!addresses.All(IsPublic))
            throw new HttpRequestException("That address is not on the public internet.");

        var socket = new Socket(SocketType.Stream, ProtocolType.Tcp) { NoDelay = true };
        try
        {
            // The checked addresses, and only those. `ConnectAsync(IPAddress[], …)` never re-resolves.
            await socket.ConnectAsync(addresses, endPoint.Port, cancellationToken);
            return new NetworkStream(socket, ownsSocket: true);
        }
        catch
        {
            socket.Dispose();
            throw;
        }
    }
}
