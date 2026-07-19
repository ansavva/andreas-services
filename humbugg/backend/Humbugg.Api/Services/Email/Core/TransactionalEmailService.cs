namespace Humbugg.Api.Services.Email.Core;

/// <summary>
/// Coordinates idempotent delivery of application-rendered transactional email.
/// </summary>
public interface ITransactionalEmailService
{
    /// <summary>
    /// Sends a message unless its deterministic message ID is already being handled.
    /// </summary>
    Task<EmailSendResult> SendAsync(TransactionalEmail email, CancellationToken cancellationToken = default);
}

/// <summary>
/// Delivers a rendered message to the runtime-specific email boundary.
/// </summary>
internal interface IEmailTransport
{
    /// <summary>
    /// Transfers ownership of a message and returns the accepting system's message identifier.
    /// </summary>
    Task<string> SendAsync(TransactionalEmail email, CancellationToken cancellationToken);
}

/// <summary>
/// Reserves message IDs and records whether an attempted handoff was accepted or failed.
/// </summary>
internal interface IEmailDeliveryLedger
{
    /// <summary>
    /// Atomically reserves a message for delivery, returning false when it is already handled.
    /// </summary>
    Task<bool> TryBeginAsync(TransactionalEmail email, CancellationToken cancellationToken);

    /// <summary>Records that the transport durably accepted the message.</summary>
    Task MarkAcceptedAsync(string messageId, CancellationToken cancellationToken);

    /// <summary>Releases a failed reservation so a later attempt can retry it.</summary>
    Task MarkFailedAsync(string messageId, CancellationToken cancellationToken);
}

/// <summary>
/// Applies Humbugg's idempotency rules around the configured email transport.
/// </summary>
internal sealed class TransactionalEmailService(
    IEmailTransport transport,
    IEmailDeliveryLedger ledger,
    IEmailPreferenceGate preferences,
    ILogger<TransactionalEmailService> logger) : ITransactionalEmailService
{
    /// <inheritdoc />
    public async Task<EmailSendResult> SendAsync(
        TransactionalEmail email,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(email);

        // Honor the recipient's opt-out before reserving a delivery slot. Essential categories are always
        // allowed by the gate; non-essential ones are skipped for opted-out recipients. Returning a normal
        // (suppressed) result rather than throwing keeps batch and reminder jobs iterating cleanly.
        if (!await preferences.IsAllowedAsync(email, cancellationToken))
        {
            logger.LogInformation(
                "Suppressed non-essential transactional email {MessageId} in category {Category}; recipient opted out",
                email.MessageId,
                email.Category);
            return new EmailSendResult(email.MessageId, email.Category, false, true, null);
        }

        if (!await ledger.TryBeginAsync(email, cancellationToken))
        {
            logger.LogInformation(
                "Skipped already handled transactional email {MessageId} in category {Category}",
                email.MessageId,
                email.Category);
            return new EmailSendResult(email.MessageId, email.Category, true, false, null);
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
        return new EmailSendResult(email.MessageId, email.Category, false, false, acceptedMessageId);
    }
}
