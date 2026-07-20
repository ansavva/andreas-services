using Humbugg.Api.Models;
using Humbugg.Api.Services;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.Formats.Gif;
using SixLabors.ImageSharp.Formats.Jpeg;
using SixLabors.ImageSharp.Formats.Png;
using SixLabors.ImageSharp.PixelFormats;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class AvatarImageTests
{
    // ─── Payload decoding / rejection ─────────────────────────────────────────

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void RejectsEmptyPayload(string? image)
    {
        var error = Assert.Throws<ApiException>(() => AvatarImage.Normalize(image));
        Assert.Equal(400, error.StatusCode);
    }

    [Fact]
    public void RejectsNonBase64Payload()
    {
        var error = Assert.Throws<ApiException>(() => AvatarImage.Normalize("not valid base64!!!"));
        Assert.Equal(400, error.StatusCode);
    }

    [Fact]
    public void RejectsBytesThatAreNotAnImage()
    {
        var payload = Convert.ToBase64String("this is definitely not an image, just plain text bytes."u8.ToArray());
        var error = Assert.Throws<ApiException>(() => AvatarImage.Normalize(payload));
        Assert.Equal(400, error.StatusCode);
        Assert.Contains("image", error.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void RejectsDisallowedContentTypeInDataUrl()
    {
        // Even though the bytes could decode, the declared data-URL type is not on the allow-list.
        var gif = EncodeGif(64, 64);
        var dataUrl = $"data:image/gif;base64,{Convert.ToBase64String(gif)}";
        var error = Assert.Throws<ApiException>(() => AvatarImage.Normalize(dataUrl));
        Assert.Equal(400, error.StatusCode);
    }

    [Fact]
    public void RejectsDisallowedActualFormatEvenWhenDeclaredTypeIsAllowed()
    {
        // Declared PNG, but the real bytes are a GIF: the actual decoded format is authoritative.
        var gif = EncodeGif(64, 64);
        var dataUrl = $"data:image/png;base64,{Convert.ToBase64String(gif)}";
        var error = Assert.Throws<ApiException>(() => AvatarImage.Normalize(dataUrl));
        Assert.Equal(400, error.StatusCode);
    }

    [Fact]
    public void RejectsImageSmallerThanMinimumDimensions()
    {
        var tiny = EncodePng(AvatarImage.MinSourceDimension - 1, AvatarImage.MinSourceDimension - 1);
        var error = Assert.Throws<ApiException>(() => AvatarImage.NormalizeBytes(tiny));
        Assert.Equal(400, error.StatusCode);
        Assert.Contains("at least", error.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void RejectsPayloadLargerThanTheSizeCeiling()
    {
        // A base64 string longer than the allowed encoded length is rejected before any decode work.
        var oversized = new string('A', (int)(AvatarImage.MaxBytes / 3 * 4) + 128);
        var error = Assert.Throws<ApiException>(() => AvatarImage.Normalize(oversized));
        Assert.Equal(400, error.StatusCode);
        Assert.Contains("MB", error.Message);
    }

    // ─── Successful normalization ─────────────────────────────────────────────

    [Fact]
    public void NormalizesValidPngToSquareJpeg()
    {
        var png = EncodePng(800, 600);
        var result = AvatarImage.NormalizeBytes(png);

        Assert.Equal("image/jpeg", result.ContentType);
        Assert.Equal("jpg", result.Extension);
        var info = Image.Identify(result.Bytes);
        Assert.Equal(AvatarImage.OutputSize, info.Width);
        Assert.Equal(AvatarImage.OutputSize, info.Height);
        Assert.IsType<JpegFormat>(info.Metadata.DecodedImageFormat);
    }

    [Fact]
    public void AcceptsBareBase64WithoutDataUrlPrefix()
    {
        var jpeg = EncodeJpeg(400, 400);
        var result = AvatarImage.Normalize(Convert.ToBase64String(jpeg));
        Assert.Equal("image/jpeg", result.ContentType);
    }

    [Fact]
    public void StripsExifMetadataFromTheStoredImage()
    {
        using var source = new Image<Rgba32>(300, 300);
        source.Metadata.ExifProfile = new SixLabors.ImageSharp.Metadata.Profiles.Exif.ExifProfile();
        source.Metadata.ExifProfile.SetValue(
            SixLabors.ImageSharp.Metadata.Profiles.Exif.ExifTag.Copyright, "secret");
        using var buffer = new MemoryStream();
        source.Save(buffer, new PngEncoder());

        var result = AvatarImage.NormalizeBytes(buffer.ToArray());

        var normalized = Image.Load(result.Bytes);
        Assert.Null(normalized.Metadata.ExifProfile);
    }

    // ─── Helpers ──────────────────────────────────────────────────────────────

    private static byte[] EncodePng(int width, int height)
    {
        using var image = new Image<Rgba32>(width, height, new Rgba32(120, 40, 200, 255));
        using var stream = new MemoryStream();
        image.Save(stream, new PngEncoder());
        return stream.ToArray();
    }

    private static byte[] EncodeJpeg(int width, int height)
    {
        using var image = new Image<Rgba32>(width, height, new Rgba32(10, 160, 90, 255));
        using var stream = new MemoryStream();
        image.Save(stream, new JpegEncoder());
        return stream.ToArray();
    }

    private static byte[] EncodeGif(int width, int height)
    {
        using var image = new Image<Rgba32>(width, height, new Rgba32(200, 200, 10, 255));
        using var stream = new MemoryStream();
        image.Save(stream, new GifEncoder());
        return stream.ToArray();
    }
}
