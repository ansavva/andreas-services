using System.Text.RegularExpressions;
using Humbugg.Api.Models;

namespace Humbugg.Api.Services;

internal static partial class CustomizationValidation
{
    public static ExchangeCustomization Validate(UpdateCustomizationRequest request)
    {
        var greeting = Text(request.Greeting, 160, "greeting");
        var instructions = Text(request.Instructions, 1500, "instructions");
        return new(greeting, instructions);
    }

    private static string Text(string? value, int max, string name)
    {
        var text = (value ?? "").Trim();
        if (text.Length > max) throw ApiException.BadRequest($"{name} must be {max} characters or fewer.");
        if (UnsafeMarkup().IsMatch(text)) throw ApiException.BadRequest($"{name} cannot contain HTML or links.");
        return text;
    }
    [GeneratedRegex(@"<[^>]*>|https?://|www\.", RegexOptions.IgnoreCase)]
    private static partial Regex UnsafeMarkup();
}
