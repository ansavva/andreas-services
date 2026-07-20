using System.Collections.Concurrent;
using Amazon.S3;
using Amazon.S3.Model;
using Humbugg.Api.Models;

namespace Humbugg.Api.Data;

/// <summary>
/// Object storage for normalized avatar images. The stored key is what the profile row references;
/// the public URL is derived from it by <c>ProfileService</c>. Implementations must never grant public
/// write access — objects are put with the Lambda's own least-privilege credentials and served
/// read-only through CloudFront.
/// </summary>
internal interface IAvatarStore
{
    Task<string> SaveAsync(string userId, NormalizedAvatarBytes image, CancellationToken cancellationToken = default);
    Task DeleteAsync(string key, CancellationToken cancellationToken = default);
    string ReadUrl(string key, string fallbackBaseUrl);
}

internal readonly record struct NormalizedAvatarBytes(byte[] Bytes, string ContentType, string Extension);

/// <summary>
/// S3-backed avatar store. Keys are namespaced per user with a random suffix so replacing an avatar
/// yields a new URL (defeating stale CloudFront caches) and one user can never overwrite another's
/// object. Objects are private; CloudFront reads them via Origin Access Control.
/// </summary>
internal sealed class S3AvatarStore(IAmazonS3 s3, HumbuggSettings settings) : IAvatarStore
{
    private readonly bool usePresignedReads = string.Equals(
        Environment.GetEnvironmentVariable("HUMBUGG_AVATAR_PRESIGNED_READS"), "true",
        StringComparison.OrdinalIgnoreCase);

    public async Task<string> SaveAsync(string userId, NormalizedAvatarBytes image, CancellationToken cancellationToken = default)
    {
        var key = $"avatars/{userId}/{Guid.NewGuid():N}.{image.Extension}";
        using var stream = new MemoryStream(image.Bytes, writable: false);
        await s3.PutObjectAsync(new PutObjectRequest
        {
            BucketName = settings.AppBucket,
            Key = key,
            InputStream = stream,
            ContentType = image.ContentType,
            // Immutable content — the key changes on every upload, so it can be cached hard downstream.
            Headers = { CacheControl = "public, max-age=31536000, immutable" },
            DisablePayloadSigning = false,
        }, cancellationToken);
        return key;
    }

    public async Task DeleteAsync(string key, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(key)) return;
        await s3.DeleteObjectAsync(new DeleteObjectRequest
        {
            BucketName = settings.AppBucket,
            Key = key,
        }, cancellationToken);
    }

    public string ReadUrl(string key, string fallbackBaseUrl) => usePresignedReads
        ? s3.GetPreSignedURL(new GetPreSignedUrlRequest
        {
            BucketName = settings.AppBucket,
            Key = key,
            Verb = HttpVerb.GET,
            Expires = DateTime.UtcNow.AddHours(1),
        })
        : $"{fallbackBaseUrl.TrimEnd('/')}/{key}";
}

/// <summary>
/// In-memory avatar store for local development and tests, used whenever no avatars bucket is
/// configured. It keeps bytes in-process so the upload flow works end to end without S3; the derived
/// URL will not resolve to a real object, which is acceptable outside production.
/// </summary>
internal sealed class InMemoryAvatarStore : IAvatarStore
{
    public ConcurrentDictionary<string, NormalizedAvatarBytes> Objects { get; } = new(StringComparer.Ordinal);

    public Task<string> SaveAsync(string userId, NormalizedAvatarBytes image, CancellationToken cancellationToken = default)
    {
        var key = $"avatars/{userId}/{Guid.NewGuid():N}.{image.Extension}";
        Objects[key] = image;
        return Task.FromResult(key);
    }

    public Task DeleteAsync(string key, CancellationToken cancellationToken = default)
    {
        if (!string.IsNullOrWhiteSpace(key)) Objects.TryRemove(key, out _);
        return Task.CompletedTask;
    }

    public string ReadUrl(string key, string fallbackBaseUrl) => $"{fallbackBaseUrl.TrimEnd('/')}/{key}";
}
