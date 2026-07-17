namespace Humbugg.Api.Services.Email.Core;

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
    Task MarkAcceptedAsync(string messageId, CancellationToken cancellationToken);
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

        string acceptedMessageId;
        try
        {
            acceptedMessageId = await transport.SendAsync(email, cancellationToken);
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

        // Mailer durably owns the message once it returns 202. Keep the reservation
        // non-retryable even if this acknowledgement is interrupted; a later Mailer
        // status event will still reconcile the delivery record.
        await ledger.MarkAcceptedAsync(email.MessageId, cancellationToken);
        logger.LogInformation(
            "Mailer accepted transactional email {MessageId} in category {Category}",
            email.MessageId,
            email.Category);
        return new EmailSendResult(email.MessageId, email.Category, false, acceptedMessageId);
    }
}
