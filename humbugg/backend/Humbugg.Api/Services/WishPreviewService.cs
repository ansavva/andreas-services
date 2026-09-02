using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.RegularExpressions;
using System.Web;
using Humbugg.Api.Data;
using Humbugg.Api.Models;

namespace Humbugg.Api.Services;

/// <summary>
/// Turns a pasted product URL into fields somebody can edit (#129).
/// </summary>
/// <remarks>
/// <para>
/// Two rules govern everything below. **Nothing fetched is trusted**: the response is a string an
/// attacker chose, so every field is length-capped, stripped of control characters and returned as
/// text that the app renders as text. And **nothing fetched is required**: a page that times out, is
/// too big, answers with a PDF or is simply hostile yields no fields, and the wish form carries on
/// as the manual form it already was. A link preview that can block somebody from adding a wish is
/// worse than no link preview.
/// </para>
/// <para>
/// The network safety — which addresses may be dialled at all — is <see cref="WishUrlSafety"/>.
/// </para>
/// </remarks>
public interface IWishPreviewService
{
    Task<WishPreview> PreviewAsync(string groupId, WishPreviewRequest request, CancellationToken cancellationToken = default);
}

internal sealed class WishPreviewService(
    ICurrentUser user,
    IGroupRepository groups,
    IMembershipRepository memberships,
    IHttpClientFactory clients,
    ILogger<WishPreviewService> logger) : IWishPreviewService
{
    /// <summary>The named client wired with the guarded connect callback in Program.cs.</summary>
    internal const string ClientName = "wish-preview";

    /// <summary>Enough for any product page's head; small enough that a hostile one cannot be a bill.</summary>
    internal const int MaxBytes = 512 * 1024;

    /// <summary>
    /// Redirects are followed by hand, so each hop is re-judged.
    /// </summary>
    /// <remarks>
    /// `AllowAutoRedirect` is off: the handler would follow a 302 from a public page to
    /// <c>http://169.254.169.254/</c> using the same guarded callback — which does hold — but it
    /// would also follow to a different port, to a credential-bearing URL, and around a loop. Doing
    /// it here means every hop goes through the same front-door checks the first one did.
    /// </remarks>
    internal const int MaxRedirects = 3;

    internal static readonly TimeSpan Timeout = TimeSpan.FromSeconds(5);

    public async Task<WishPreview> PreviewAsync(
        string groupId,
        WishPreviewRequest request,
        CancellationToken cancellationToken = default)
    {
        await RequireMembershipAsync(groupId, cancellationToken);

        var raw = (request.Url ?? "").Trim();
        if (raw.Length is 0 or > WishValidation.MaxUrlLength || !Uri.TryCreate(raw, UriKind.Absolute, out var uri))
            throw ApiException.BadRequest("Paste a complete http:// or https:// link.");

        // Refusals decidable from the URL itself are reported plainly: the person typed it, so
        // nothing is disclosed by explaining it, and a clear message beats a silent failure.
        var refusal = WishUrlSafety.Inspect(uri);
        if (refusal != WishUrlSafety.Refusal.None) throw ApiException.BadRequest(Explain(refusal));

        // Everything past this point is uniform on failure. A refusal that needed DNS or a
        // connection must not be distinguishable from a page that simply did not answer — the
        // difference between "blocked, it is internal" and "nothing there" is a port scanner, and
        // the reply and the timing both have to keep that quiet.
        try
        {
            return await FetchAsync(uri, cancellationToken);
        }
        catch (Exception exception) when (exception is not ApiException)
        {
            logger.LogInformation("A wishlist link preview did not complete for {Host}.", uri.Host);
            return WishPreview.Unavailable(uri);
        }
    }

    private async Task<WishPreview> FetchAsync(Uri uri, CancellationToken cancellationToken)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(Timeout);
        var client = clients.CreateClient(ClientName);

        var current = uri;
        for (var hop = 0; ; hop++)
        {
            using var message = new HttpRequestMessage(HttpMethod.Get, current);
            // Asking for HTML makes a well-behaved server send HTML, and gives a hostile one nothing
            // it did not already have.
            message.Headers.Accept.ParseAdd("text/html,application/xhtml+xml");
            using var response = await client.SendAsync(
                message, HttpCompletionOption.ResponseHeadersRead, deadline.Token);

            if (IsRedirect(response.StatusCode) && response.Headers.Location is { } location)
            {
                if (hop >= MaxRedirects) return WishPreview.Unavailable(uri);
                var next = location.IsAbsoluteUri ? location : new Uri(current, location);
                // Every hop through the same front door as the first. A redirect is just another URL
                // somebody else chose, and this one was chosen by the page rather than by the user.
                if (WishUrlSafety.Inspect(next) != WishUrlSafety.Refusal.None) return WishPreview.Unavailable(uri);
                current = next;
                continue;
            }

            if (!response.IsSuccessStatusCode) return WishPreview.Unavailable(uri);
            // Only HTML is parsed. A 300MB video that happens to be at a product URL is not read,
            // and neither is anything whose type says it is not a page.
            var mediaType = response.Content.Headers.ContentType?.MediaType;
            if (mediaType is not ("text/html" or "application/xhtml+xml")) return WishPreview.Unavailable(uri);

            var html = await ReadCappedAsync(response.Content, deadline.Token);
            return Extract(uri, current, html);
        }
    }

    /// <summary>
    /// Reads at most <see cref="MaxBytes"/>, whatever the response claims.
    /// </summary>
    /// <remarks>
    /// Deliberately not `Content-Length`: that is a number the remote server chose, and a server
    /// that wants this process to allocate a gigabyte will happily say 4KB and then send one. The
    /// cap is on what is actually read.
    /// </remarks>
    private static async Task<string> ReadCappedAsync(HttpContent content, CancellationToken cancellationToken)
    {
        await using var stream = await content.ReadAsStreamAsync(cancellationToken);
        var buffer = new byte[8 * 1024];
        var collected = new MemoryStream();
        int read;
        while (collected.Length < MaxBytes &&
               (read = await stream.ReadAsync(buffer, cancellationToken)) > 0)
        {
            collected.Write(buffer, 0, (int)Math.Min(read, MaxBytes - collected.Length));
        }
        // Whatever the bytes are, they are read as UTF-8 with replacement rather than throwing: a
        // page in another encoding yields mojibake in a field the user can edit, which is a better
        // outcome than no preview at all.
        return Encoding.UTF8.GetString(collected.ToArray());
    }

    private static bool IsRedirect(HttpStatusCode status) =>
        status is HttpStatusCode.MovedPermanently or HttpStatusCode.Found or HttpStatusCode.SeeOther
            or HttpStatusCode.TemporaryRedirect or HttpStatusCode.PermanentRedirect;

    // ── Extraction ──────────────────────────────────────────────────────────────────────────────

    /// <summary>
    /// Pulls the four fields out of the markup.
    /// </summary>
    /// <remarks>
    /// `NonBacktracking` on every pattern: these run over a document an attacker wrote, and a
    /// backtracking regex on hostile input is a denial of service that needs no network at all.
    /// It costs some regex features and buys a linear-time guarantee.
    /// </remarks>
    private static readonly RegexOptions Safe =
        RegexOptions.IgnoreCase | RegexOptions.NonBacktracking | RegexOptions.CultureInvariant;

    private static readonly Regex MetaTag = new("<meta[^>]+>", Safe);
    private static readonly Regex TitleTag = new("<title[^>]*>([^<]{0,500})", Safe);
    private static readonly Regex CanonicalTag = new("<link[^>]+rel=[\"']?canonical[\"']?[^>]*>", Safe);
    private static readonly Regex Attribute = new("([a-z:-]{1,40})\\s*=\\s*(\"[^\"]{0,2000}\"|'[^']{0,2000}')", Safe);

    internal static WishPreview Extract(Uri requested, Uri final, string html)
    {
        var meta = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var tag in MetaTag.Matches(html).Take(400).Select(match => match.Value))
        {
            var attributes = Attributes(tag);
            var key = attributes.GetValueOrDefault("property") ?? attributes.GetValueOrDefault("name");
            var value = attributes.GetValueOrDefault("content");
            if (key is null || value is null) continue;
            // First one wins. A page that repeats og:title is either sloppy or trying something.
            meta.TryAdd(key, value);
        }

        var title = Text(meta.GetValueOrDefault("og:title")
            ?? meta.GetValueOrDefault("twitter:title")
            ?? TitleTag.Match(html).Groups[1].Value, WishValidation.MaxTitleLength);

        var image = Link(meta.GetValueOrDefault("og:image") ?? meta.GetValueOrDefault("twitter:image"), final);

        var canonicalHref = Attributes(CanonicalTag.Match(html).Value).GetValueOrDefault("href")
            ?? meta.GetValueOrDefault("og:url");
        // The canonical falls back to the URL actually fetched, not the one pasted: a redirect that
        // resolved a tracking link to the real product page is exactly what should be stored.
        var canonical = Link(canonicalHref, final) ?? final.ToString();

        var (priceCents, currency) = Price(
            meta.GetValueOrDefault("product:price:amount") ?? meta.GetValueOrDefault("og:price:amount"),
            meta.GetValueOrDefault("product:price:currency") ?? meta.GetValueOrDefault("og:price:currency"));

        return new WishPreview(
            Host: final.Host,
            Fetched: title is not null || image is not null || priceCents is not null,
            Title: title,
            ImageUrl: image,
            CanonicalUrl: canonical,
            PriceCents: priceCents,
            Currency: currency);
    }

    private static Dictionary<string, string> Attributes(string tag)
    {
        var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        if (tag.Length == 0) return values;
        foreach (Match match in Attribute.Matches(tag).Take(40))
            values.TryAdd(match.Groups[1].Value, HttpUtility.HtmlDecode(match.Groups[2].Value[1..^1]));
        return values;
    }

    /// <summary>
    /// Normalises a string a stranger wrote so it is safe to store and to render as text.
    /// </summary>
    /// <remarks>
    /// Control characters go — including the bidirectional overrides that can make a title render as
    /// something other than what it says — newlines collapse to spaces, and the whole thing is
    /// capped at the same length a hand-typed title is. It is never HTML: the app puts it in a
    /// `Text`, and the email templates HTML-encode everything they are given.
    /// </remarks>
    internal static string? Text(string? value, int max)
    {
        if (string.IsNullOrWhiteSpace(value)) return null;
        var decoded = HttpUtility.HtmlDecode(value);
        // Control characters AND Unicode format characters. `char.IsControl` covers category Cc and
        // misses Cf entirely — which is where U+202E RIGHT-TO-LEFT OVERRIDE lives, the character that
        // makes a title render as something other than what it says. Stripping only Cc would leave
        // the one that actually deceives.
        var cleaned = new string(decoded
            .Select(character => char.IsControl(character) ||
                char.GetUnicodeCategory(character) == System.Globalization.UnicodeCategory.Format
                ? ' '
                : character)
            .ToArray());
        cleaned = Regex.Replace(cleaned, @"\s{2,}", " ", RegexOptions.NonBacktracking).Trim();
        if (cleaned.Length == 0) return null;
        return cleaned.Length <= max ? cleaned : cleaned[..max].TrimEnd();
    }

    /// <summary>
    /// A URL from the page, resolved against it and held to the same rules as the one pasted.
    /// </summary>
    /// <remarks>
    /// An `og:image` is a URL an attacker chose and the app will put in an `Image` — so
    /// `javascript:`, `data:` and a private address all have to die here. It is never fetched by
    /// Humbugg; the browser loads it, which is why the scheme check matters as much as the address.
    /// </remarks>
    internal static string? Link(string? value, Uri baseUri)
    {
        var text = Text(value, WishValidation.MaxUrlLength);
        if (text is null) return null;

        // "Absolute" is not the same question as "has a scheme we want". On Unix, `Uri.TryCreate`
        // parses a leading-slash path as an absolute **file** URI — so `/img/knife.jpg` becomes
        // `file:///img/knife.jpg` and never reaches the relative branch at all. `Inspect` refuses it,
        // so nothing unsafe happens; the image is simply lost. Asking for the scheme up front is what
        // makes a site-relative og:image resolve.
        Uri? absolute;
        if (Uri.TryCreate(text, UriKind.Absolute, out var parsed) &&
            parsed.Scheme is var scheme && (scheme == Uri.UriSchemeHttp || scheme == Uri.UriSchemeHttps))
            absolute = parsed;
        else if (!Uri.TryCreate(baseUri, text, out absolute))
            return null;

        // Still inspected, whichever branch produced it: resolving `javascript:alert(1)` against a
        // base yields `javascript:alert(1)`, and this is what refuses it.
        return WishUrlSafety.Inspect(absolute) == WishUrlSafety.Refusal.None ? absolute.ToString() : null;
    }

    private static (long? Cents, string? Currency) Price(string? amount, string? currency)
    {
        var text = Text(amount, 32);
        if (text is null) return (null, null);
        // Invariant parsing only. A page saying "1.234,56" is ambiguous between locales, and a
        // preview that silently turns £12.34 into £1234 is worse than one that offers no price.
        if (!decimal.TryParse(text, System.Globalization.NumberStyles.Number,
                System.Globalization.CultureInfo.InvariantCulture, out var value)) return (null, null);
        if (value < 0 || value > 1_000_000) return (null, null);
        // Read at full length and then judged — NOT truncated to three and then checked, which turns
        // "dollars please" into the perfectly plausible currency code "DOL".
        var code = Text(currency, 32)?.ToUpperInvariant();
        return ((long)Math.Round(value * 100), code is { Length: 3 } && code.All(char.IsAsciiLetter) ? code : null);
    }

    private static string Explain(WishUrlSafety.Refusal refusal) => refusal switch
    {
        WishUrlSafety.Refusal.HasCredentials => "Paste the link without a username and password in it.",
        WishUrlSafety.Refusal.UnusualPort => "Humbugg only reads links on the standard web ports.",
        WishUrlSafety.Refusal.LiteralPrivateAddress => "That link points somewhere private rather than at a public web page.",
        _ => "Paste a complete http:// or https:// link.",
    };

    private async Task RequireMembershipAsync(string groupId, CancellationToken cancellationToken)
    {
        _ = await groups.GetAsync(groupId, cancellationToken) ?? throw ApiException.NotFound("Group not found.");
        _ = await memberships.GetByUserAndGroupAsync(user.UserId, groupId, cancellationToken)
            ?? throw ApiException.Forbidden("You are not a member of this group.");
    }
}
