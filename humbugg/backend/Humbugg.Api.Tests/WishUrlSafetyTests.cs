using System.Net;
using Humbugg.Api.Services;
using Xunit;

namespace Humbugg.Api.Tests;

/// <summary>
/// Which addresses Humbugg's servers will dial on a participant's say-so (#129).
/// </summary>
/// <remarks>
/// This is the security surface of wishlist link previews, and the failure mode of a gap here is not
/// a broken preview — it is the API making an authenticated request from inside the VPC to an
/// address somebody pasted into a text box. Every range below is a range somebody has exfiltrated
/// credentials through in a real incident somewhere.
/// </remarks>
public sealed class WishUrlSafetyTests
{
    /// <summary>
    /// The address that matters most, in the four notations that reach it.
    /// </summary>
    /// <remarks>
    /// 169.254.169.254 is the cloud instance-metadata service. On an instance without IMDSv2
    /// enforced it hands role credentials to anything that can make an HTTP request from it, which
    /// is the single highest-value target an SSRF can have.
    /// </remarks>
    [Theory]
    [InlineData("169.254.169.254")]
    [InlineData("169.254.170.2")]                    // ECS task metadata
    [InlineData("::ffff:169.254.169.254")]           // IPv4-mapped IPv6
    [InlineData("fe80::1")]                          // IPv6 link-local
    public void TheMetadataServiceAndItsNeighboursAreNotPublic(string address)
    {
        Assert.False(WishUrlSafety.IsPublic(IPAddress.Parse(address)));
    }

    [Theory]
    [InlineData("127.0.0.1")]
    [InlineData("127.1.2.3")]
    [InlineData("::1")]
    [InlineData("::ffff:127.0.0.1")]                 // loopback in an IPv6 costume
    [InlineData("0.0.0.0")]
    [InlineData("::")]
    [InlineData("10.0.0.5")]
    [InlineData("172.16.0.1")]
    [InlineData("172.31.255.254")]
    [InlineData("192.168.1.1")]
    [InlineData("100.64.0.1")]                       // carrier-grade NAT
    [InlineData("192.0.0.1")]                        // IETF protocol assignments
    [InlineData("198.18.0.1")]                       // benchmarking
    [InlineData("224.0.0.1")]                        // multicast
    [InlineData("255.255.255.255")]                  // broadcast
    [InlineData("fc00::1")]                          // IPv6 unique-local
    [InlineData("fd12:3456::1")]
    public void PrivateAndReservedAddressesAreNotPublic(string address)
    {
        Assert.False(WishUrlSafety.IsPublic(IPAddress.Parse(address)));
    }

    /// <summary>
    /// The near misses. A range check that is one octet too greedy breaks the whole feature.
    /// </summary>
    [Theory]
    [InlineData("93.184.216.34")]                    // example.com
    [InlineData("172.15.0.1")]                       // just below 172.16/12
    [InlineData("172.32.0.1")]                       // just above
    [InlineData("192.167.0.1")]                      // just below 192.168/16
    [InlineData("192.169.0.1")]                      // just above
    [InlineData("100.63.255.255")]                   // just below 100.64/10
    [InlineData("100.128.0.1")]                      // just above
    [InlineData("169.253.0.1")]                      // just below link-local
    [InlineData("169.255.0.1")]                      // just above
    [InlineData("198.17.0.1")]
    [InlineData("198.20.0.1")]
    [InlineData("2606:2800:220:1:248:1893:25c8:1946")] // a real public IPv6
    public void OrdinaryPublicAddressesArePublic(string address)
    {
        Assert.True(WishUrlSafety.IsPublic(IPAddress.Parse(address)));
    }

    [Theory]
    [InlineData("ftp://example.com/thing", "NotAbsoluteHttp")]
    [InlineData("file:///etc/passwd", "NotAbsoluteHttp")]
    [InlineData("gopher://example.com:70/_", "NotAbsoluteHttp")]
    // Credentials would be sent to a third party, and `https://apple.com@evil.test/` reads like
    // Apple to almost everybody.
    [InlineData("https://user:pass@example.com/", "HasCredentials")]
    // Anything but 80/443 is a port scan waiting to happen: 6379 is Redis, 9200 Elasticsearch.
    [InlineData("http://example.com:6379/", "UnusualPort")]
    [InlineData("http://example.com:22/", "UnusualPort")]
    // A literal private address needs no DNS to judge, so it gets the clearer answer.
    [InlineData("http://127.0.0.1/admin", "LiteralPrivateAddress")]
    [InlineData("http://169.254.169.254/latest/meta-data/", "LiteralPrivateAddress")]
    [InlineData("http://[::1]/", "LiteralPrivateAddress")]
    [InlineData("http://10.0.0.1/", "LiteralPrivateAddress")]
    // The expectation is the enum's NAME rather than the value: xUnit requires a public test class,
    // and `WishUrlSafety.Refusal` is internal like every other service type here. Naming it in a
    // string keeps the class internal without an InternalsVisibleTo just for a test signature.
    public void HostileUrlsAreRefusedBeforeAnyPacketIsSent(string url, string expected)
    {
        Assert.Equal(expected, WishUrlSafety.Inspect(new Uri(url)).ToString());
    }

    [Theory]
    [InlineData("https://example.com/product/1")]
    [InlineData("http://example.com/product/1")]
    [InlineData("https://example.com:443/p")]
    [InlineData("http://example.com:80/p")]
    [InlineData("https://shop.example.co.uk/a/b?c=d#e")]
    public void OrdinaryProductUrlsAreAccepted(string url)
    {
        Assert.Equal("None", WishUrlSafety.Inspect(new Uri(url)).ToString());
    }

    /// <summary>
    /// A hostname that resolves anywhere private is refused at connect time.
    /// </summary>
    /// <remarks>
    /// The name is the attack: `localtest.me` and a hundred services like it are public DNS records
    /// that answer 127.0.0.1, so a check on the STRING would pass every one of them. This is also
    /// why the check lives in the connect callback rather than in a caller — the resolution that is
    /// judged has to be the resolution that is dialled, or DNS can answer differently the second
    /// time.
    /// </remarks>
    [Fact]
    public async Task AHostnameResolvingToLoopbackIsRefusedAtConnectTime()
    {
        var error = await Assert.ThrowsAsync<HttpRequestException>(() =>
            WishUrlSafety.ConnectAsync(
                new DnsEndPoint("localhost", 80), TestContext.Current.CancellationToken).AsTask());

        Assert.Contains("public internet", error.Message, StringComparison.Ordinal);
    }
}
