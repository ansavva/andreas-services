using Humbugg.Api.Models;

namespace Humbugg.Api.Services;

internal static class WishValidation
{
    public const int MaxWishesPerMember = 100;
    public const int MaxTitleLength = 200;
    public const int MaxUrlLength = 2048;
    public const int MaxDetailsLength = 1000;
    public const int MaxQuantity = 99;

    // One hundred million minor units — $1,000,000. A cap exists so a typo cannot store a number that
    // later overflows a client's formatter or renders as a joke price on the giver's screen.
    public const long MaxPriceCents = 100_000_000;

    public static string Title(string? value) =>
        Validation.Required(value, "title", MaxTitleLength);

    public static string Details(string? value) =>
        Validation.Optional(value, MaxDetailsLength);

    // Format only. This deliberately does NOT fetch the URL — resolving a pasted link into product
    // metadata is #129, and doing it here would put an SSRF surface behind an innocuous-looking
    // create call. What this guarantees is that whatever is stored is an absolute http(s) URL, so a
    // client rendering it as a link cannot be handed `javascript:` or `data:`.
    public static string Url(string? value, string field)
    {
        var trimmed = value?.Trim() ?? "";
        if (trimmed.Length is 0) return "";
        if (trimmed.Length > MaxUrlLength)
            throw ApiException.BadRequest($"{field} must be {MaxUrlLength} characters or fewer.");
        if (!Uri.TryCreate(trimmed, UriKind.Absolute, out var uri) ||
            (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps))
            throw ApiException.BadRequest($"{field} must be a complete http:// or https:// address.");
        return uri.ToString();
    }

    public static int Quantity(int? value)
    {
        var quantity = value ?? 1;
        if (quantity is < 1 or > MaxQuantity)
            throw ApiException.BadRequest($"quantity must be between 1 and {MaxQuantity}.");
        return quantity;
    }

    public static long? PriceCents(long? value)
    {
        if (value is null) return null;
        if (value is < 0 or > MaxPriceCents)
            throw ApiException.BadRequest($"price_cents must be between 0 and {MaxPriceCents}.");
        return value;
    }

    // Defaults to the group's currency rather than a hardcoded USD, so a wish priced in an exchange
    // that is not in dollars does not silently claim to be.
    public static string Currency(string? value, string groupCurrency)
    {
        var trimmed = (value ?? "").Trim();
        if (trimmed.Length is 0) return groupCurrency;
        if (trimmed.Length != 3 || !trimmed.All(char.IsAsciiLetter))
            throw ApiException.BadRequest("currency must be a three-letter ISO 4217 code.");
        return trimmed.ToUpperInvariant();
    }

    public static WishKind Kind(string? value) =>
        Parse(value, WishKind.Product, "kind");

    public static WishPriority Priority(string? value) =>
        Parse(value, WishPriority.Normal, "priority");

    private static TEnum Parse<TEnum>(string? value, TEnum fallback, string field) where TEnum : struct, Enum
    {
        var trimmed = (value ?? "").Trim();
        if (trimmed.Length is 0) return fallback;
        if (!Enum.TryParse<TEnum>(trimmed, ignoreCase: true, out var parsed) || !Enum.IsDefined(parsed))
            throw ApiException.BadRequest(
                $"{field} must be one of: {string.Join(", ", Enum.GetNames<TEnum>().Select(name => name.ToLowerInvariant()))}.");
        return parsed;
    }
}
