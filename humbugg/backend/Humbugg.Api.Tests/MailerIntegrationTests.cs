using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using Amazon.Runtime;
using Humbugg.Api.Email.Adapters.Aws;
using Humbugg.Api.Email.Adapters.Http;
using Humbugg.Api.Email.Core;
using Humbugg.Api.Email.Functions;
using Microsoft.Extensions.Logging.Abstractions;
using System.Net;
using System.Text;
using System.Text.Json;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class MailerIntegrationTests
{
    [Fact]
    public async Task UnsignedClientSubmitsTheVersionedHumbuggContract()
    {
        var handler = new RecordingHttpHandler(_ => new HttpResponseMessage(HttpStatusCode.Accepted)
        {
            Content = new StringContent(
                """{"schema_version":1,"application_message_id":"hmb_invitation_test","status":"accepted"}""",
                Encoding.UTF8,
                "application/json")
        });
        var client = new MailerClient(
            new HttpClient(handler) { BaseAddress = new Uri("http://mailer.test") },
            Settings(),
            new UnsignedMailerRequestSigner());
        var email = new TransactionalEmail(
            "hmb_invitation_test",
            EmailCategory.Invitation,
            "recipient@example.com",
            "An invitation",
            "<p>Hello</p>",
            "Hello");

        var result = await client.SubmitMessageAsync(
            email,
            cancellationToken: TestContext.Current.CancellationToken);

        Assert.Equal("hmb_invitation_test", result.ApplicationMessageId);
        var sent = Assert.Single(handler.Requests);
        Assert.Equal(
            "/v1/services/humbugg/messages",
            sent.Request.RequestUri?.AbsolutePath);
        Assert.Null(sent.Request.Headers.Authorization);
        using var body = JsonDocument.Parse(sent.Body!);
        Assert.Equal(1, body.RootElement.GetProperty("schema_version").GetInt32());
        Assert.Equal("invitation", body.RootElement.GetProperty("category").GetString());
        Assert.Equal("exchange", body.RootElement.GetProperty("message_class").GetString());
        Assert.Empty(body.RootElement.GetProperty("attachments").EnumerateArray());
        Assert.False(body.RootElement.TryGetProperty("service_id", out _));
        Assert.False(body.RootElement.TryGetProperty("from_address", out _));
    }

    [Fact]
    public async Task AttachmentRegistrationAndUploadUseTheReturnedHeaders()
    {
        var handler = new RecordingHttpHandler(request =>
        {
            if (request.Method == HttpMethod.Post)
            {
                return new HttpResponseMessage(HttpStatusCode.Created)
                {
                    Content = new StringContent(
                        """
                        {
                          "schema_version": 1,
                          "attachment_id": "att_test",
                          "upload_url": "http://uploads.test/v1/development-uploads/token",
                          "required_headers": {
                            "content-type": "application/pdf",
                            "x-mailer-content-sha256": "abc123"
                          },
                          "expires_at": "2026-07-17T13:00:00Z"
                        }
                        """,
                        Encoding.UTF8,
                        "application/json")
                };
            }
            return new HttpResponseMessage(HttpStatusCode.NoContent);
        });
        var client = new MailerClient(
            new HttpClient(handler) { BaseAddress = new Uri("http://mailer.test") },
            Settings(),
            new UnsignedMailerRequestSigner());

        var upload = await client.RequestAttachmentUploadAsync(
            new MailerAttachmentUploadRequest(
                1,
                "hmb_invitation_test",
                "guide.pdf",
                "application/pdf",
                3,
                new string('a', 64)),
            TestContext.Current.CancellationToken);
        await client.UploadAttachmentAsync(
            upload,
            new MemoryStream([1, 2, 3]),
            TestContext.Current.CancellationToken);

        Assert.Equal(2, handler.Requests.Count);
        Assert.Equal(
            "/v1/services/humbugg/attachment-uploads",
            handler.Requests[0].Request.RequestUri?.AbsolutePath);
        Assert.Equal(HttpMethod.Put, handler.Requests[1].Request.Method);
        Assert.Equal(
            "application/pdf",
            handler.Requests[1].Request.Content?.Headers.ContentType?.MediaType);
        Assert.Equal(
            "abc123",
            handler.Requests[1].Request.Headers.GetValues("x-mailer-content-sha256").Single());
    }

    [Fact]
    public async Task ProductionSignerAddsExecuteApiSigV4Headers()
    {
        var signer = new AwsSigV4MailerRequestSigner(
            new SessionAWSCredentials("access", "secret", "token"),
            "us-east-1");
        using var request = new HttpRequestMessage(
            HttpMethod.Post,
            "https://mailer-api.andreas.services/v1/services/humbugg/messages")
        {
            Content = new ByteArrayContent("{}"u8.ToArray())
        };
        request.Content.Headers.ContentType =
            System.Net.Http.Headers.MediaTypeHeaderValue.Parse("application/json");

        await signer.SignAsync(
            request,
            "{}"u8.ToArray(),
            TestContext.Current.CancellationToken);

        Assert.Equal("AWS4-HMAC-SHA256", request.Headers.Authorization?.Scheme);
        Assert.Contains(
            "/us-east-1/execute-api/aws4_request",
            request.Headers.Authorization?.Parameter);
        Assert.True(request.Headers.Contains("x-amz-date"));
        Assert.True(request.Headers.Contains("x-amz-content-sha256"));
        Assert.Equal("token", request.Headers.GetValues("x-amz-security-token").Single());
    }

    [Fact]
    public async Task StatusHandlerStoresNormalizedStateWithNinetyDayExpiry()
    {
        using var db = new RecordingDynamoDb();
        var handler = new EmailStatusHandler(
            db,
            "humbugg-email-messages",
            NullLogger<EmailStatusHandler>.Instance);
        var occurredAt = DateTimeOffset.Parse("2026-07-17T12:00:00Z");

        await handler.ApplyAsync(
            new MailerStatusEvent(
                1,
                "event-1",
                "humbugg",
                "hmb_invitation_test",
                "invitation",
                "exchange",
                "delivery",
                occurredAt,
                "ses-message-id",
                "provider detail that must not be stored"),
            TestContext.Current.CancellationToken);

        var request = Assert.IsType<UpdateItemRequest>(db.Request);
        Assert.Equal("humbugg-email-messages", request.TableName);
        Assert.Equal("hmb_invitation_test", request.Key["message_id"].S);
        Assert.Equal("delivery", request.ExpressionAttributeValues[":status"].S);
        Assert.Equal("30", request.ExpressionAttributeValues[":rank"].N);
        Assert.Equal(
            occurredAt.AddDays(90).ToUnixTimeSeconds().ToString(),
            request.ExpressionAttributeValues[":expires_at"].N);
        Assert.DoesNotContain(
            request.ExpressionAttributeValues.Values,
            value => value.S?.Contains("provider detail", StringComparison.Ordinal) == true);
    }

    [Fact]
    public async Task StatusHandlerRejectsEventsForAnotherService()
    {
        using var db = new RecordingDynamoDb();
        var handler = new EmailStatusHandler(
            db,
            "humbugg-email-messages",
            NullLogger<EmailStatusHandler>.Instance);

        await Assert.ThrowsAsync<InvalidOperationException>(() => handler.ApplyAsync(
            new MailerStatusEvent(
                1,
                "event-1",
                "storybook",
                "message-1",
                "invitation",
                "exchange",
                "accepted",
                DateTimeOffset.UtcNow,
                null,
                null),
            TestContext.Current.CancellationToken));
    }

    private static HumbuggSettings Settings() => new(
        AwsRegion: "us-east-1",
        CognitoRegion: "us-east-1",
        CognitoUserPoolId: "pool",
        CognitoClientId: "client",
        CorsOrigin: "http://localhost",
        AppBaseUrl: "http://localhost",
        DynamoDbEndpointUrl: null,
        ProfilesTable: "profiles",
        GroupsTable: "groups",
        GroupMembersTable: "members",
        DrawsTable: "draws",
        AuditEventsTable: "audit",
        EmailProvider: "mailer",
        EmailMessagesTable: "emails",
        MailerBaseUrl: "http://mailer.test",
        MailerAuthMode: "none",
        MailerServiceId: "humbugg");

    private sealed class RecordingHttpHandler(
        Func<HttpRequestMessage, HttpResponseMessage> response) : HttpMessageHandler
    {
        public List<(HttpRequestMessage Request, byte[]? Body)> Requests { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            var body = request.Content is null
                ? null
                : await request.Content.ReadAsByteArrayAsync(cancellationToken);
            Requests.Add((request, body));
            return response(request);
        }
    }

    private sealed class RecordingDynamoDb() : AmazonDynamoDBClient(
        new BasicAWSCredentials("access", "secret"),
        new AmazonDynamoDBConfig
        {
            ServiceURL = "http://127.0.0.1:1",
            AuthenticationRegion = "us-east-1"
        })
    {
        public UpdateItemRequest? Request { get; private set; }

        public override Task<UpdateItemResponse> UpdateItemAsync(
            UpdateItemRequest request,
            CancellationToken cancellationToken = default)
        {
            Request = request;
            return Task.FromResult(new UpdateItemResponse());
        }
    }
}
