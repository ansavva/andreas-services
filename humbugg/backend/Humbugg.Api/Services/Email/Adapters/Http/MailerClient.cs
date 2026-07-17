using Humbugg.Api.Services.Email.Core;
using System.Net;
using System.Net.Http.Headers;
using System.Text.Json;

namespace Humbugg.Api.Services.Email.Adapters.Http;

internal interface IMailerClient
{
    Task<MailerAcceptedResponse> SubmitMessageAsync(
        TransactionalEmail email,
        IReadOnlyCollection<MailerAttachmentReference>? attachments = null,
        CancellationToken cancellationToken = default);

    Task<MailerAttachmentUpload> RequestAttachmentUploadAsync(
        MailerAttachmentUploadRequest request,
        CancellationToken cancellationToken = default);

    Task UploadAttachmentAsync(
        MailerAttachmentUpload upload,
        Stream content,
        CancellationToken cancellationToken = default);
}

internal sealed class MailerClient(
    HttpClient http,
    HumbuggSettings settings,
    IMailerRequestSigner signer) : IMailerClient
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower
    };

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

    private static async Task<T> DeserializeAsync<T>(
        HttpResponseMessage response,
        CancellationToken cancellationToken)
    {
        await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
        return await JsonSerializer.DeserializeAsync<T>(stream, JsonOptions, cancellationToken)
            ?? throw new MailerApiException("Mailer returned an empty response.");
    }

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

internal interface IMailerRequestSigner
{
    Task SignAsync(
        HttpRequestMessage request,
        ReadOnlyMemory<byte> body,
        CancellationToken cancellationToken);
}

internal sealed class MailerApiException(
    string message,
    HttpStatusCode? statusCode = null,
    string? requestId = null) : Exception(message)
{
    public HttpStatusCode? StatusCode { get; } = statusCode;
    public string? RequestId { get; } = requestId;
}

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

internal sealed record MailerAttachmentReference(
    string AttachmentId,
    string Disposition = "attachment",
    string? ContentId = null);

internal sealed record MailerAttachmentUploadRequest(
    int SchemaVersion,
    string ApplicationMessageId,
    string FileName,
    string ContentType,
    long SizeBytes,
    string Sha256);

internal sealed record MailerAttachmentUpload(
    int SchemaVersion,
    string AttachmentId,
    Uri UploadUrl,
    IReadOnlyDictionary<string, string> RequiredHeaders,
    DateTimeOffset ExpiresAt);

internal sealed record MailerAcceptedResponse(
    int SchemaVersion,
    string ApplicationMessageId,
    string Status);
