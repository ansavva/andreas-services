using Humbugg.Api.Services.Email.Core;

namespace Humbugg.Api.Tests;

/// <summary>Records every message; asserted on by the tests that care and ignored by the rest.</summary>
internal sealed class NoopEmail : ITransactionalEmailService
{
    public List<TransactionalEmail> Sent { get; } = [];

    /// <summary>Makes every send fail, for the callers that must survive a broken mailer.</summary>
    public bool Throw { get; init; }

    public Task<EmailSendResult> SendAsync(TransactionalEmail email, CancellationToken cancellationToken = default)
    {
        if (Throw) throw new InvalidOperationException("mail is down");
        Sent.Add(email);
        return Task.FromResult(new EmailSendResult(email.MessageId, email.Category, false, false, email.MessageId));
    }
}
