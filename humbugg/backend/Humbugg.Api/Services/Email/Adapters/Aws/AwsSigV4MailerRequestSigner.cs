using Amazon.Runtime;
using Humbugg.Api.Services.Email.Adapters.Http;
using System.Globalization;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;

namespace Humbugg.Api.Services.Email.Adapters.Aws;

// Production signs the shared HTTP contract with the Lambda role's credentials.
internal sealed class AwsSigV4MailerRequestSigner(
    AWSCredentials credentials,
    string region,
    TimeProvider? timeProvider = null) : IMailerRequestSigner
{
    private readonly TimeProvider clock = timeProvider ?? TimeProvider.System;

    public async Task SignAsync(
        HttpRequestMessage request,
        ReadOnlyMemory<byte> body,
        CancellationToken cancellationToken)
    {
        if (request.RequestUri is null || !request.RequestUri.IsAbsoluteUri)
            throw new InvalidOperationException("Mailer requests must have an absolute URI before signing.");

        var immutable = await credentials.GetCredentialsAsync();
        cancellationToken.ThrowIfCancellationRequested();
        var timestamp = clock.GetUtcNow().UtcDateTime;
        var amzDate = timestamp.ToString("yyyyMMdd'T'HHmmss'Z'", CultureInfo.InvariantCulture);
        var date = timestamp.ToString("yyyyMMdd", CultureInfo.InvariantCulture);
        var payloadHash = Hex(SHA256.HashData(body.Span));

        request.Headers.Host = request.RequestUri.IsDefaultPort
            ? request.RequestUri.Host
            : request.RequestUri.Authority;
        request.Headers.TryAddWithoutValidation("x-amz-date", amzDate);
        request.Headers.TryAddWithoutValidation("x-amz-content-sha256", payloadHash);
        if (immutable.UseToken)
            request.Headers.TryAddWithoutValidation("x-amz-security-token", immutable.Token);

        var headers = new SortedDictionary<string, string>(StringComparer.Ordinal)
        {
            ["content-type"] = request.Content?.Headers.ContentType?.ToString() ?? "application/json",
            ["host"] = request.Headers.Host,
            ["x-amz-content-sha256"] = payloadHash,
            ["x-amz-date"] = amzDate
        };
        if (immutable.UseToken)
            headers["x-amz-security-token"] = immutable.Token;

        var canonicalHeaders = string.Concat(headers.Select(item => $"{item.Key}:{Normalize(item.Value)}\n"));
        var signedHeaders = string.Join(';', headers.Keys);
        var canonicalRequest = string.Join(
            '\n',
            request.Method.Method,
            CanonicalPath(request.RequestUri),
            request.RequestUri.Query.TrimStart('?'),
            canonicalHeaders,
            signedHeaders,
            payloadHash);
        var scope = $"{date}/{region}/execute-api/aws4_request";
        var stringToSign = string.Join(
            '\n',
            "AWS4-HMAC-SHA256",
            amzDate,
            scope,
            Hex(SHA256.HashData(Encoding.UTF8.GetBytes(canonicalRequest))));
        var signingKey = Hmac(
            Hmac(
                Hmac(
                    Hmac(Encoding.UTF8.GetBytes($"AWS4{immutable.SecretKey}"), date),
                    region),
                "execute-api"),
            "aws4_request");
        var signature = Hex(Hmac(signingKey, stringToSign));
        request.Headers.Authorization = new AuthenticationHeaderValue(
            "AWS4-HMAC-SHA256",
            $"Credential={immutable.AccessKey}/{scope}, SignedHeaders={signedHeaders}, Signature={signature}");
    }

    private static string CanonicalPath(Uri uri) =>
        string.Join('/', uri.AbsolutePath.Split('/').Select(Uri.EscapeDataString));

    private static string Normalize(string value) =>
        string.Join(' ', value.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries));

    private static byte[] Hmac(byte[] key, string value) =>
        HMACSHA256.HashData(key, Encoding.UTF8.GetBytes(value));

    private static string Hex(ReadOnlySpan<byte> value) => Convert.ToHexStringLower(value);
}
