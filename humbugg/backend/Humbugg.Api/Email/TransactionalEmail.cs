using System.Security.Cryptography;
using System.Text;

namespace Humbugg.Api.Email;

public enum EmailCategory
{
    Invitation,
    Reminder,
    DrawCompleted,
    AssignmentAvailable,
    AccountExchangeEvent
}

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

    public string MessageId { get; }
    public EmailCategory Category { get; }
    public string ToAddress { get; }
    public string Subject { get; }
    public string HtmlBody { get; }
    public string TextBody { get; }
}

public sealed record EmailSendResult(
    string MessageId,
    EmailCategory Category,
    bool AlreadyHandled,
    string? AcceptedMessageId);

public static class EmailMessageId
{
    public static string Create(EmailCategory category, string eventId, string toAddress)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(eventId);
        ArgumentException.ThrowIfNullOrWhiteSpace(toAddress);

        var identity = $"{category}:{eventId.Trim()}:{toAddress.Trim().ToLowerInvariant()}";
        var hash = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(identity)));
        return $"hmb_{CategoryName(category)}_{hash[..24]}";
    }

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
