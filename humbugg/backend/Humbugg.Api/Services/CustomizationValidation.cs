using System.Text.RegularExpressions;
using Humbugg.Api.Models;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.Formats.Jpeg;
using SixLabors.ImageSharp.Processing;

namespace Humbugg.Api.Services;

internal static partial class CustomizationValidation
{
    public static ExchangeCustomization Validate(UpdateCustomizationRequest request)
    {
        var greeting = Text(request.Greeting, 160, "greeting");
        var instructions = Text(request.Instructions, 1500, "instructions");
        var primary = Color(request.PrimaryColor, "#7C2D12");
        var accent = Color(request.AccentColor, "#F59E0B");
        return new(greeting, instructions, primary, accent, Image(request.Image));
    }

    private static string Text(string? value, int max, string name)
    {
        var text = (value ?? "").Trim();
        if (text.Length > max) throw ApiException.BadRequest($"{name} must be {max} characters or fewer.");
        if (UnsafeMarkup().IsMatch(text)) throw ApiException.BadRequest($"{name} cannot contain HTML or links.");
        return text;
    }
    private static string Color(string? value, string fallback)
    {
        var color = string.IsNullOrWhiteSpace(value) ? fallback : value.Trim().ToUpperInvariant();
        if (!HexColor().IsMatch(color)) throw ApiException.BadRequest("Theme colors must use #RRGGBB.");
        return color;
    }
    private static string? Image(string? payload)
    {
        if (string.IsNullOrWhiteSpace(payload)) return null;
        var bytes = AvatarImage.DecodePayload(payload);
        using var image = SixLabors.ImageSharp.Image.Load(bytes);
        if (image.Width > 6000 || image.Height > 6000) throw ApiException.BadRequest("The image is too large.");
        image.Metadata.ExifProfile = null; image.Metadata.IptcProfile = null; image.Metadata.XmpProfile = null;
        image.Mutate(x => x.Resize(new ResizeOptions { Size = new(1200, 600), Mode = ResizeMode.Crop }));
        using var output = new MemoryStream();
        image.Save(output, new JpegEncoder { Quality = 72 });
        if (output.Length > 240_000) throw ApiException.BadRequest("The processed image is too large.");
        return $"data:image/jpeg;base64,{Convert.ToBase64String(output.ToArray())}";
    }

    [GeneratedRegex(@"<[^>]*>|https?://|www\.", RegexOptions.IgnoreCase)]
    private static partial Regex UnsafeMarkup();
    [GeneratedRegex(@"^#[0-9A-F]{6}$")]
    private static partial Regex HexColor();
}
