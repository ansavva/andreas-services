using System.Security.Cryptography;
using System.Text;

namespace Humbugg.Api.Services.Email.Core;

/// <summary>
/// Identifies the application-owned reason for sending a transactional message.
/// The Mailer registration restricts Humbugg to these categories.
/// </summary>
public enum EmailCategory
{
    Invitation,
    Reminder,
    DrawCompleted,
    AssignmentAvailable,
    AccountExchangeEvent
}

/// <summary>
/// Represents a fully rendered, single-recipient message ready for the Mailer service.
/// Sender identity and delivery configuration are deliberately not caller-controlled.
/// </summary>
public sealed record TransactionalEmail
{
    internal TransactionalEmail(
        string messageId,
        EmailCategory category,
        string toAddress,
        string subject,
        string htmlBody,
        string textBody)
    {
        MessageId = messageId;
        Category = category;
        ToAddress = toAddress;
        Subject = subject;
        HtmlBody = htmlBody;
        TextBody = textBody;
    }

    /// <summary>Gets Humbugg's deterministic idempotency key for the message.</summary>
    public string MessageId { get; }

    /// <summary>Gets the application-owned message category.</summary>
    public EmailCategory Category { get; }

    /// <summary>Gets the message's sole recipient.</summary>
    public string ToAddress { get; }

    /// <summary>Gets the rendered subject.</summary>
    public string Subject { get; }

    /// <summary>Gets the rendered HTML alternative.</summary>
    public string HtmlBody { get; }

    /// <summary>Gets the rendered plain-text alternative.</summary>
    public string TextBody { get; }
}

/// <summary>
/// Describes the result of handing a transactional message to its configured transport.
/// </summary>
public sealed record EmailSendResult(
    string MessageId,
    EmailCategory Category,
    bool AlreadyHandled,
    string? AcceptedMessageId);

/// <summary>
/// Creates stable Mailer application-message identifiers from business-event identity.
/// </summary>
public static class EmailMessageId
{
    /// <summary>
    /// Creates the same opaque identifier for retries of the same category, event, and recipient.
    /// </summary>
    public static string Create(EmailCategory category, string eventId, string toAddress)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(eventId);
        ArgumentException.ThrowIfNullOrWhiteSpace(toAddress);

        var identity = $"{category}:{eventId.Trim()}:{toAddress.Trim().ToLowerInvariant()}";
        var hash = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(identity)));
        return $"hmb_{CategoryName(category)}_{hash[..24]}";
    }

    /// <summary>
    /// Converts the application enum to the category registered in Mailer's HTTP contract.
    /// </summary>
    internal static string CategoryName(EmailCategory category) => category switch
    {
        EmailCategory.Invitation => "invitation",
        EmailCategory.Reminder => "reminder",
        EmailCategory.DrawCompleted => "draw_completed",
        EmailCategory.AssignmentAvailable => "assignment_available",
        EmailCategory.AccountExchangeEvent => "account_exchange_event",
        _ => throw new ArgumentOutOfRangeException(nameof(category), category, null)
    };
}
