using Humbugg.Api.Services.Email.Adapters.Memory;
using Humbugg.Api.Services.Email.Core;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class TransactionalEmailTests
{
    private static readonly Uri ActionUrl = new("https://humbugg.com/app/groups/group-1");

    [Fact]
    public void MessageIdsAreStableByCategoryEventAndRecipient()
    {
        var first = EmailMessageId.Create(EmailCategory.Invitation, "invite-123", "PERSON@example.com");
        var retry = EmailMessageId.Create(EmailCategory.Invitation, "invite-123", "person@example.com");
        var differentCategory = EmailMessageId.Create(EmailCategory.Reminder, "invite-123", "person@example.com");

        Assert.Equal(first, retry);
        Assert.NotEqual(first, differentCategory);
        Assert.StartsWith("hmb_invitation_", first);
    }

    [Fact]
    public async Task RepeatedSendIsCapturedOnlyOnce()
    {
        var capture = new CapturingEmailTransport();
        var service = new TransactionalEmailService(
            capture,
            new InMemoryEmailDeliveryLedger(),
            new AllowAllEmailPreferenceGate(),
            NullLogger<TransactionalEmailService>.Instance);
        var email = Templates().Invitation(new(
            "invite-123",
            "person@example.com",
            "Pat",
            "Alex",
            "Family exchange",
            ActionUrl));

        var first = await service.SendAsync(email, TestContext.Current.CancellationToken);
        var retry = await service.SendAsync(email, TestContext.Current.CancellationToken);

        Assert.False(first.AlreadyHandled);
        Assert.True(retry.AlreadyHandled);
        Assert.Single(capture.Messages);
        Assert.Equal(email.MessageId, capture.Messages[0].MessageId);
    }

    [Fact]
    public async Task FailedDeliveryCanBeRetriedWithTheSameMessageId()
    {
        var transport = new FailOnceTransport();
        var service = new TransactionalEmailService(
            transport,
            new InMemoryEmailDeliveryLedger(),
            new AllowAllEmailPreferenceGate(),
            NullLogger<TransactionalEmailService>.Instance);
        var email = Templates().Reminder(new(
            "reminder-123",
            "person@example.com",
            "Pat",
            "Family exchange",
            "Please finish your wishlist.",
            ActionUrl));

        await Assert.ThrowsAsync<InvalidOperationException>(() => service.SendAsync(email, TestContext.Current.CancellationToken));
        var retry = await service.SendAsync(email, TestContext.Current.CancellationToken);

        Assert.False(retry.AlreadyHandled);
        Assert.Equal(2, transport.Attempts);
    }

    [Fact]
    public async Task MailerAcceptanceIsNotSubmittedAgainWhenLedgerAcknowledgementFails()
    {
        var transport = new CountingTransport();
        var service = new TransactionalEmailService(
            transport,
            new AcknowledgementFailingLedger(),
            new AllowAllEmailPreferenceGate(),
            NullLogger<TransactionalEmailService>.Instance);
        var email = Templates().Reminder(new(
            "reminder-ack-1",
            "person@example.com",
            "Pat",
            "Family exchange",
            "Please finish your wishlist.",
            ActionUrl));

        await Assert.ThrowsAsync<InvalidOperationException>(() => service.SendAsync(email, TestContext.Current.CancellationToken));
        var retry = await service.SendAsync(email, TestContext.Current.CancellationToken);

        Assert.True(retry.AlreadyHandled);
        Assert.Equal(1, transport.Attempts);
    }

    [Fact]
    public void TemplatesCoverEveryTransactionalCategoryWithAccessibleMultipartContent()
    {
        var templates = Templates();
        var messages = new[]
        {
            templates.Invitation(new("invite-1", "person@example.com", "Pat", "Alex", "Family exchange", ActionUrl)),
            templates.Reminder(new("reminder-1", "person@example.com", "Pat", "Family exchange", "Please finish your wishlist.", ActionUrl)),
            templates.DrawCompleted(new("draw-1", "person@example.com", "Pat", "Family exchange", ActionUrl)),
            templates.AssignmentAvailable(new("assignment-1", "person@example.com", "Pat", "Family exchange", ActionUrl)),
            templates.AccountExchangeEvent(new("event-1", "person@example.com", "Pat", "Family exchange", "The exchange date changed.", "Review the new date", ActionUrl))
        };

        Assert.Equal(Enum.GetValues<EmailCategory>(), messages.Select(message => message.Category));
        Assert.All(messages, message =>
        {
            Assert.Contains("<html lang=\"en\">", message.HtmlBody);
            Assert.Contains("<main>", message.HtmlBody);
            Assert.Contains("<h1>", message.HtmlBody);
            Assert.Contains("<a href=", message.HtmlBody);
            Assert.Contains(ActionUrl.AbsoluteUri, message.TextBody);
            Assert.DoesNotContain("unsubscribe", message.HtmlBody, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("offer", message.TextBody, StringComparison.OrdinalIgnoreCase);
        });
    }

    [Fact]
    public void TemplateValuesAreEscapedAndCannotInjectHeadersOrMarkup()
    {
        var email = Templates().Invitation(new(
            "invite-1",
            "person@example.com",
            "<Pat>",
            "Alex\r\nBcc: attacker@example.com",
            "Family & friends",
            ActionUrl));

        Assert.DoesNotContain("<Pat>", email.HtmlBody);
        Assert.Contains("&lt;Pat&gt;", email.HtmlBody);
        Assert.DoesNotContain('\r', email.Subject);
        Assert.DoesNotContain('\n', email.Subject);
    }

    private static ITransactionalEmailTemplates Templates() => new TransactionalEmailTemplates();

    private sealed class FailOnceTransport : IEmailTransport
    {
        public int Attempts { get; private set; }

        public Task<string> SendAsync(TransactionalEmail email, CancellationToken cancellationToken)
        {
            Attempts++;
            if (Attempts == 1) throw new InvalidOperationException("Simulated provider failure.");
            return Task.FromResult(email.MessageId);
        }
    }

    private sealed class CountingTransport : IEmailTransport
    {
        public int Attempts { get; private set; }

        public Task<string> SendAsync(TransactionalEmail email, CancellationToken cancellationToken)
        {
            Attempts++;
            return Task.FromResult(email.MessageId);
        }
    }

    private sealed class AcknowledgementFailingLedger : IEmailDeliveryLedger
    {
        private bool reserved;

        public Task<bool> TryBeginAsync(TransactionalEmail email, CancellationToken cancellationToken)
        {
            if (reserved) return Task.FromResult(false);
            reserved = true;
            return Task.FromResult(true);
        }

        public Task MarkAcceptedAsync(string messageId, CancellationToken cancellationToken) =>
            throw new InvalidOperationException("Simulated ledger acknowledgement failure.");

        public Task MarkFailedAsync(string messageId, CancellationToken cancellationToken) => Task.CompletedTask;
    }
}
