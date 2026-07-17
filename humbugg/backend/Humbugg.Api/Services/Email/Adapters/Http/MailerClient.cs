using Humbugg.Api.Services.Email.Core;
using System.Net;
using System.Net.Http.Headers;
using System.Text.Json;

namespace Humbugg.Api.Services.Email.Adapters.Http;

/// <summary>
/// Defines Humbugg's client-side operations against the shared Mailer HTTP contract.
/// </summary>
internal interface IMailerClient
{
    /// <summary>
    /// Submits a rendered message and optional previously uploaded attachments.
    /// </summary>
    Task<MailerAcceptedResponse> SubmitMessageAsync(
        TransactionalEmail email,
        IReadOnlyCollection<MailerAttachmentReference>? attachments = null,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Registers attachment metadata and obtains a restricted upload location.
    /// </summary>
    Task<MailerAttachmentUpload> RequestAttachmentUploadAsync(
        MailerAttachmentUploadRequest request,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Uploads attachment bytes using the URL and required headers issued by Mailer.
    /// </summary>
    Task UploadAttachmentAsync(
        MailerAttachmentUpload upload,
        Stream content,
        CancellationToken cancellationToken = default);
}

/// <summary>
/// Serializes, signs, and sends Humbugg requests using Mailer's versioned HTTP schema.
/// </summary>
internal sealed class MailerClient(
    HttpClient http,
    HumbuggSettings settings,
    IMailerRequestSigner signer) : IMailerClient
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower
    };

    /// <inheritdoc />
    public async Task<MailerAcceptedResponse> SubmitMessageAsync(
        TransactionalEmail email,
        IReadOnlyCollection<MailerAttachmentReference>? attachments = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(email);
        var request = new MailerMessageRequest(
            1,
            email.MessageId,
            EmailMessageId.CategoryName(email.Category),
            "exchange",
            email.ToAddress,
            email.Subject,
            email.HtmlBody,
            email.TextBody,
            attachments ?? []);

        using var response = await SendJsonAsync(
            HttpMethod.Post,
            $"/v1/services/{Uri.EscapeDataString(settings.MailerServiceId)}/messages",
            request,
            cancellationToken);
        await EnsureSuccessAsync(response, HttpStatusCode.Accepted, cancellationToken);
        return await DeserializeAsync<MailerAcceptedResponse>(response, cancellationToken);
    }

    /// <inheritdoc />
    public async Task<MailerAttachmentUpload> RequestAttachmentUploadAsync(
        MailerAttachmentUploadRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await SendJsonAsync(
            HttpMethod.Post,
            $"/v1/services/{Uri.EscapeDataString(settings.MailerServiceId)}/attachment-uploads",
            request,
            cancellationToken);
        await EnsureSuccessAsync(response, HttpStatusCode.Created, cancellationToken);
        return await DeserializeAsync<MailerAttachmentUpload>(response, cancellationToken);
    }

    /// <inheritdoc />
    public async Task UploadAttachmentAsync(
        MailerAttachmentUpload upload,
        Stream content,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(upload);
        ArgumentNullException.ThrowIfNull(content);
        using var request = new HttpRequestMessage(HttpMethod.Put, upload.UploadUrl)
        {
            Content = new StreamContent(content)
        };
        foreach (var (name, value) in upload.RequiredHeaders)
        {
            if (name.Equals("content-type", StringComparison.OrdinalIgnoreCase))
                request.Content.Headers.ContentType = MediaTypeHeaderValue.Parse(value);
            else if (!request.Headers.TryAddWithoutValidation(name, value))
                request.Content.Headers.TryAddWithoutValidation(name, value);
        }

        using var response = await http.SendAsync(request, cancellationToken);
        if (response.StatusCode is not HttpStatusCode.OK and not HttpStatusCode.NoContent)
            await EnsureSuccessAsync(response, HttpStatusCode.NoContent, cancellationToken);
    }

    /// <summary>
    /// Serializes an API request, gives the configured runtime signer the exact body
    /// bytes, and sends the resulting HTTP message.
    /// </summary>
    private async Task<HttpResponseMessage> SendJsonAsync<T>(
        HttpMethod method,
        string path,
        T value,
        CancellationToken cancellationToken)
    {
        var body = JsonSerializer.SerializeToUtf8Bytes(value, JsonOptions);
        if (http.BaseAddress is null)
            throw new InvalidOperationException("Mailer HTTP client requires a base address.");
        using var request = new HttpRequestMessage(method, new Uri(http.BaseAddress, path))
        {
            Content = new ByteArrayContent(body)
        };
        request.Content.Headers.ContentType = new MediaTypeHeaderValue("application/json")
        {
            CharSet = "utf-8"
        };
        await signer.SignAsync(request, body, cancellationToken);
        return await http.SendAsync(request, cancellationToken);
    }

    /// <summary>Deserializes a non-empty Mailer response using its snake-case contract.</summary>
    private static async Task<T> DeserializeAsync<T>(
        HttpResponseMessage response,
        CancellationToken cancellationToken)
    {
        await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
        return await JsonSerializer.DeserializeAsync<T>(stream, JsonOptions, cancellationToken)
            ?? throw new MailerApiException("Mailer returned an empty response.");
    }

    /// <summary>
    /// Converts an unexpected HTTP response into a privacy-safe application exception.
    /// The response body is deliberately excluded because it may contain message data.
    /// </summary>
    private static async Task EnsureSuccessAsync(
        HttpResponseMessage response,
        HttpStatusCode expected,
        CancellationToken cancellationToken)
    {
        if (response.StatusCode == expected) return;
        var requestId = response.Headers.TryGetValues("x-amzn-requestid", out var values)
            ? values.FirstOrDefault()
            : null;
        await response.Content.LoadIntoBufferAsync(cancellationToken);
        throw new MailerApiException(
            $"Mailer request failed with HTTP {(int)response.StatusCode}.",
            response.StatusCode,
            requestId);
    }
}

/// <summary>
/// Applies runtime-specific authentication to a serialized Mailer API request.
/// </summary>
internal interface IMailerRequestSigner
{
    /// <summary>
    /// Signs the request in place; local implementations may intentionally do nothing.
    /// </summary>
    Task SignAsync(
        HttpRequestMessage request,
        ReadOnlyMemory<byte> body,
        CancellationToken cancellationToken);
}

/// <summary>
/// Represents a failed Mailer API operation without retaining a sensitive response body.
/// </summary>
internal sealed class MailerApiException(
    string message,
    HttpStatusCode? statusCode = null,
    string? requestId = null) : Exception(message)
{
    /// <summary>Gets the HTTP status returned by Mailer, when available.</summary>
    public HttpStatusCode? StatusCode { get; } = statusCode;

    /// <summary>Gets AWS's request identifier for operational correlation, when available.</summary>
    public string? RequestId { get; } = requestId;
}

/// <summary>Defines the versioned wire request for submitting one message.</summary>
internal sealed record MailerMessageRequest(
    int SchemaVersion,
    string ApplicationMessageId,
    string Category,
    string MessageClass,
    string ToAddress,
    string Subject,
    string HtmlBody,
    string TextBody,
    IReadOnlyCollection<MailerAttachmentReference> Attachments);

/// <summary>References attachment content already registered and uploaded with Mailer.</summary>
internal sealed record MailerAttachmentReference(
    string AttachmentId,
    string Disposition = "attachment",
    string? ContentId = null);

/// <summary>Defines the versioned metadata used to register an attachment upload.</summary>
internal sealed record MailerAttachmentUploadRequest(
    int SchemaVersion,
    string ApplicationMessageId,
    string FileName,
    string ContentType,
    long SizeBytes,
    string Sha256);

/// <summary>Contains Mailer's restricted upload URL and the headers required to use it.</summary>
internal sealed record MailerAttachmentUpload(
    int SchemaVersion,
    string AttachmentId,
    Uri UploadUrl,
    IReadOnlyDictionary<string, string> RequiredHeaders,
    DateTimeOffset ExpiresAt);

/// <summary>Represents Mailer's durable acceptance of an application message.</summary>
internal sealed record MailerAcceptedResponse(
    int SchemaVersion,
    string ApplicationMessageId,
    string Status);
