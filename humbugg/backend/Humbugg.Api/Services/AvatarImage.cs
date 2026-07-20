using Humbugg.Api.Models;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.Formats;
using SixLabors.ImageSharp.Formats.Jpeg;
using SixLabors.ImageSharp.Formats.Png;
using SixLabors.ImageSharp.Formats.Webp;
using SixLabors.ImageSharp.Processing;

namespace Humbugg.Api.Services;

/// <summary>
/// The result of normalizing an uploaded avatar: re-encoded image bytes plus the content type and
/// file extension they should be stored and served with.
/// </summary>
public sealed record NormalizedAvatar(byte[] Bytes, string ContentType, string Extension);

/// <summary>
/// Validates and safely normalizes an uploaded profile photo. Untrusted image bytes are never stored
/// as-is: the header is inspected first (bounded work), the declared and actual formats must both be
/// an allowed raster type, and the image is fully re-encoded to a square JPEG. Re-encoding strips all
/// original metadata (EXIF/GPS/ICC and any trailing payload smuggled after the image), so the stored
/// object is a clean, predictable file regardless of what was uploaded.
/// </summary>
public static class AvatarImage
{
    // Raw decoded byte ceiling. Kept well below the 6 MB synchronous Lambda payload limit even after
    // base64 transport overhead (~33%), so a valid upload never exceeds what the function can receive.
    public const long MaxBytes = 3 * 1024 * 1024;

    // Bounds on the source dimensions. The upper bound caps decode cost for a hostile "image bomb";
    // the lower bound rejects degenerate 1x1 tracking pixels that would look broken as an avatar.
    public const int MaxSourceDimension = 6000;
    public const int MinSourceDimension = 32;

    // Every stored avatar is a square of this edge length, so the frontend can render it at any size
    // without layout surprises.
    public const int OutputSize = 512;

    private const int JpegQuality = 82;

    private static readonly HashSet<string> AllowedContentTypes = new(StringComparer.OrdinalIgnoreCase)
    {
        "image/jpeg", "image/jpg", "image/png", "image/webp",
    };

    /// <summary>
    /// Decodes a base64 or data-URL payload, enforcing the content-type allow-list and the raw size
    /// ceiling. Throws <see cref="ApiException"/> (400) for anything malformed or oversized.
    /// </summary>
    public static byte[] DecodePayload(string? image)
    {
        var payload = (image ?? "").Trim();
        if (payload.Length == 0) throw ApiException.BadRequest("Choose an image to upload.");

        if (payload.StartsWith("data:", StringComparison.OrdinalIgnoreCase))
        {
            var comma = payload.IndexOf(',');
            var semicolon = payload.IndexOf(';');
            if (comma < 0 || semicolon < 0 || semicolon > comma)
                throw ApiException.BadRequest("The image is not a valid data URL.");
            var declaredType = payload[5..semicolon];
            if (!AllowedContentTypes.Contains(declaredType))
                throw ApiException.BadRequest("Upload a PNG, JPEG, or WebP image.");
            payload = payload[(comma + 1)..];
        }

        // Base64 inflates the raw bytes by ~4/3, so bound the encoded length before allocating.
        if ((long)payload.Length > (MaxBytes / 3 * 4) + 4)
            throw ApiException.BadRequest($"The image must be {MaxBytes / (1024 * 1024)} MB or smaller.");

        byte[] bytes;
        try { bytes = Convert.FromBase64String(payload); }
        catch (FormatException) { throw ApiException.BadRequest("The image is not valid base64 data."); }

        if (bytes.LongLength == 0) throw ApiException.BadRequest("Choose an image to upload.");
        if (bytes.LongLength > MaxBytes)
            throw ApiException.BadRequest($"The image must be {MaxBytes / (1024 * 1024)} MB or smaller.");
        return bytes;
    }

    /// <summary>
    /// Full pipeline: decode the payload, validate the real image format and dimensions, then re-encode
    /// to a square, metadata-free JPEG. Never trusts the caller-declared type — the actual decoded
    /// format is authoritative.
    /// </summary>
    public static NormalizedAvatar Normalize(string? image) => NormalizeBytes(DecodePayload(image));

    public static NormalizedAvatar NormalizeBytes(byte[] bytes)
    {
        if (bytes is null || bytes.LongLength == 0) throw ApiException.BadRequest("Choose an image to upload.");
        if (bytes.LongLength > MaxBytes)
            throw ApiException.BadRequest($"The image must be {MaxBytes / (1024 * 1024)} MB or smaller.");

        // Inspect the header only (cheap, no full decode) to reject non-images and image bombs before
        // committing to a full decode.
        ImageInfo info;
        try { info = Image.Identify(bytes); }
        catch (Exception ex) when (ex is UnknownImageFormatException or InvalidImageContentException)
        {
            throw ApiException.BadRequest("That file is not a readable image.");
        }
        if (info is null) throw ApiException.BadRequest("That file is not a readable image.");

        EnsureAllowedFormat(info.Metadata.DecodedImageFormat);
        if (info.Width < MinSourceDimension || info.Height < MinSourceDimension)
            throw ApiException.BadRequest($"The image must be at least {MinSourceDimension}x{MinSourceDimension} pixels.");
        if (info.Width > MaxSourceDimension || info.Height > MaxSourceDimension)
            throw ApiException.BadRequest($"The image must be at most {MaxSourceDimension}x{MaxSourceDimension} pixels.");

        using var img = Image.Load(bytes);
        img.Metadata.ExifProfile = null;
        img.Metadata.IptcProfile = null;
        img.Metadata.XmpProfile = null;
        // Center-crop to a square and downscale to the fixed avatar edge. Max mode + a square target
        // makes ImageSharp cover the box and trim the overflow, so portraits and landscapes both work.
        img.Mutate(context => context.Resize(new ResizeOptions
        {
            Size = new Size(OutputSize, OutputSize),
            Mode = ResizeMode.Crop,
            Position = AnchorPositionMode.Center,
        }));

        using var output = new MemoryStream();
        img.Save(output, new JpegEncoder { Quality = JpegQuality });
        return new NormalizedAvatar(output.ToArray(), "image/jpeg", "jpg");
    }

    private static void EnsureAllowedFormat(IImageFormat? format)
    {
        var allowed = format is JpegFormat or PngFormat or WebpFormat;
        if (!allowed) throw ApiException.BadRequest("Upload a PNG, JPEG, or WebP image.");
    }
}
