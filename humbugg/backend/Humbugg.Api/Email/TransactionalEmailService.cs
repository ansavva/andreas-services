namespace Humbugg.Api.Email;

public interface ITransactionalEmailService
{
    Task<EmailSendResult> SendAsync(TransactionalEmail email, CancellationToken cancellationToken = default);
}

internal interface IEmailTransport
{
    Task<string> SendAsync(TransactionalEmail email, CancellationToken cancellationToken);
}

internal interface IEmailDeliveryLedger
{
    Task<bool> TryBeginAsync(TransactionalEmail email, CancellationToken cancellationToken);
    Task MarkSentAsync(string messageId, string providerMessageId, CancellationToken cancellationToken);
    Task MarkFailedAsync(string messageId, CancellationToken cancellationToken);
}

internal sealed class TransactionalEmailService(
    IEmailTransport transport,
    IEmailDeliveryLedger ledger,
    ILogger<TransactionalEmailService> logger) : ITransactionalEmailService
{
    public async Task<EmailSendResult> SendAsync(
        TransactionalEmail email,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(email);

        if (!await ledger.TryBeginAsync(email, cancellationToken))
        {
            logger.LogInformation(
                "Skipped already handled transactional email {MessageId} in category {Category}",
                email.MessageId,
                email.Category);
            return new EmailSendResult(email.MessageId, email.Category, true, null);
        }

        string providerMessageId;
        try
        {
            providerMessageId = await transport.SendAsync(email, cancellationToken);
        }
        catch (Exception)
        {
            try
            {
                await ledger.MarkFailedAsync(email.MessageId, CancellationToken.None);
            }
            catch (Exception ledgerException)
            {
                logger.LogError(
                    ledgerException,
                    "Could not mark failed transactional email {MessageId}; preserving the provider error",
                    email.MessageId);
            }

            throw;
        }

        // Once SES returns a provider ID, keep the reservation in its non-retryable
        // state even if this update fails. That favors duplicate prevention when the
        // provider outcome is known but the ledger acknowledgement is interrupted.
        await ledger.MarkSentAsync(email.MessageId, providerMessageId, cancellationToken);
        logger.LogInformation(
            "Sent transactional email {MessageId} in category {Category}",
            email.MessageId,
            email.Category);
        return new EmailSendResult(email.MessageId, email.Category, false, providerMessageId);
    }
}
