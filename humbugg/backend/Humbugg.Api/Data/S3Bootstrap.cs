using Amazon.S3;
using Amazon.S3.Model;
using Amazon.S3.Util;

namespace Humbugg.Api.Data;

/// <summary>
/// Local-development bootstrap for the application object bucket. Production buckets are provisioned by
/// Terraform; this service is only registered when the app runs against a local S3 endpoint (LocalStack,
/// via <c>S3_ENDPOINT_URL</c>), where the bucket starts empty. It ensures the bucket exists and — local
/// only — grants anonymous read on the <c>avatars/</c> prefix so uploaded photos render in the SPA during
/// development. It never runs against real AWS.
/// </summary>
internal sealed class S3Bootstrap(IAmazonS3 s3, HumbuggSettings settings, ILogger<S3Bootstrap> logger) : IHostedService
{
    public async Task StartAsync(CancellationToken cancellationToken)
    {
        var bucket = settings.AppBucket;
        if (string.IsNullOrWhiteSpace(bucket)) return;
        try
        {
            if (await AmazonS3Util.DoesS3BucketExistV2Async(s3, bucket)) return;
            await s3.PutBucketAsync(new PutBucketRequest { BucketName = bucket }, cancellationToken);
            // Local dev only: allow anonymous GET on avatars so the browser can display them unsigned.
            await s3.PutBucketPolicyAsync(new PutBucketPolicyRequest
            {
                BucketName = bucket,
                Policy = "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"LocalPublicReadAvatars\"," +
                         "\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":\"s3:GetObject\"," +
                         "\"Resource\":\"arn:aws:s3:::" + bucket + "/avatars/*\"}]}",
            }, cancellationToken);
            logger.LogInformation("Created local S3 bucket {Bucket}", bucket);
        }
        catch (AmazonS3Exception ex)
        {
            logger.LogWarning(ex, "Could not ensure local S3 bucket {Bucket}; avatar uploads may fail until it exists", bucket);
        }
    }

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;
}
