using System.Net.Mail;
using System.Text.Encodings.Web;
using Humbugg.Api.Models;

namespace Humbugg.Api.Services.Email.Core;

/// <summary>Contains the application data needed to render an invitation email.</summary>
public sealed record InvitationEmail(
    string EventId,
    string ToAddress,
    string RecipientName,
    string OrganizerName,
    string ExchangeName,
    Uri InvitationUrl,
    ExchangeCustomization? Customization = null);

/// <summary>Contains the application data needed to render an exchange reminder.</summary>
/// <remarks><see cref="RecipientUserId"/> is the recipient's Humbugg account id, used to honor their
/// non-essential email opt-out. Reminders are non-essential.</remarks>
public sealed record ReminderEmail(
    string EventId,
    string ToAddress,
    string RecipientName,
    string ExchangeName,
    string Reminder,
    Uri ExchangeUrl,
    string? RecipientUserId = null,
    ExchangeCustomization? Customization = null);

/// <summary>Contains the application data needed to announce a completed draw.</summary>
public sealed record DrawCompletedEmail(
    string EventId,
    string ToAddress,
    string RecipientName,
    string ExchangeName,
    Uri ExchangeUrl,
    ExchangeCustomization? Customization = null);

/// <summary>Contains the application data needed to announce an available assignment.</summary>
public sealed record AssignmentAvailableEmail(
    string EventId,
    string ToAddress,
    string RecipientName,
    string ExchangeName,
    Uri AssignmentUrl,
    ExchangeCustomization? Customization = null);

/// <summary>Contains the application data needed to render a general exchange update.</summary>
/// <remarks><see cref="RecipientUserId"/> is the recipient's Humbugg account id, used to honor their
/// non-essential email opt-out. Group-activity updates are non-essential.</remarks>
public sealed record AccountExchangeEventEmail(
    string EventId,
    string ToAddress,
    string RecipientName,
    string ExchangeName,
    string EventSummary,
    string ActionLabel,
    Uri ExchangeUrl,
    string? RecipientUserId = null,
    ExchangeCustomization? Customization = null);

/// <summary>
/// Renders Humbugg-owned product copy into transport-neutral transactional messages.
/// </summary>
public interface ITransactionalEmailTemplates
{
    /// <summary>Renders an invitation message.</summary>
    TransactionalEmail Invitation(InvitationEmail input);

    /// <summary>Renders an exchange reminder.</summary>
    TransactionalEmail Reminder(ReminderEmail input);

    /// <summary>Renders a draw-completed notification.</summary>
    TransactionalEmail DrawCompleted(DrawCompletedEmail input);

    /// <summary>Renders an assignment-available notification.</summary>
    TransactionalEmail AssignmentAvailable(AssignmentAvailableEmail input);

    /// <summary>Renders a general account or exchange event notification.</summary>
    TransactionalEmail AccountExchangeEvent(AccountExchangeEventEmail input);
}

/// <summary>
/// Validates and safely renders Humbugg's HTML and plain-text email alternatives.
/// </summary>
internal sealed class TransactionalEmailTemplates : ITransactionalEmailTemplates
{
    /// <inheritdoc />
    public TransactionalEmail Invitation(InvitationEmail input)
    {
        ArgumentNullException.ThrowIfNull(input);
        var recipient = Text(input.RecipientName);
        var organizer = Text(input.OrganizerName);
        var exchange = Text(input.ExchangeName);
        var subject = Subject($"{organizer} invited you to {exchange}");
        var intro = $"{organizer} invited you to join {exchange} on Humbugg.";
        return Create(
            EmailCategory.Invitation,
            input.EventId,
            input.ToAddress,
            subject,
            recipient,
            intro,
            "View your invitation",
            input.InvitationUrl,
            "This invitation is for an exchange you were invited to join.", customization: input.Customization);
    }

    /// <inheritdoc />
    public TransactionalEmail Reminder(ReminderEmail input)
    {
        ArgumentNullException.ThrowIfNull(input);
        var exchange = Text(input.ExchangeName);
        return Create(
            EmailCategory.Reminder,
            input.EventId,
            input.ToAddress,
            Subject($"Reminder for {exchange}"),
            Text(input.RecipientName),
            $"Reminder for {exchange}: {Text(input.Reminder)}",
            "Open the exchange",
            input.ExchangeUrl,
            "You are receiving this reminder because you participate in this exchange.",
            input.RecipientUserId, input.Customization);
    }

    /// <inheritdoc />
    public TransactionalEmail DrawCompleted(DrawCompletedEmail input)
    {
        ArgumentNullException.ThrowIfNull(input);
        var exchange = Text(input.ExchangeName);
        return Create(
            EmailCategory.DrawCompleted,
            input.EventId,
            input.ToAddress,
            Subject($"The draw for {exchange} is complete"),
            Text(input.RecipientName),
            $"The draw for {exchange} is complete. Your private assignment is ready.",
            "View your assignment",
            input.ExchangeUrl,
            "Only you can view your assignment after signing in.", customization: input.Customization);
    }

    /// <inheritdoc />
    public TransactionalEmail AssignmentAvailable(AssignmentAvailableEmail input)
    {
        ArgumentNullException.ThrowIfNull(input);
        var exchange = Text(input.ExchangeName);
        return Create(
            EmailCategory.AssignmentAvailable,
            input.EventId,
            input.ToAddress,
            Subject($"Your assignment for {exchange} is available"),
            Text(input.RecipientName),
            $"Your private assignment for {exchange} is now available.",
            "View your private assignment",
            input.AssignmentUrl,
            "Humbugg never includes the recipient's name in email. Sign in to reveal it privately.", customization: input.Customization);
    }

    /// <inheritdoc />
    public TransactionalEmail AccountExchangeEvent(AccountExchangeEventEmail input)
    {
        ArgumentNullException.ThrowIfNull(input);
        var exchange = Text(input.ExchangeName);
        return Create(
            EmailCategory.AccountExchangeEvent,
            input.EventId,
            input.ToAddress,
            Subject($"Update for {exchange}"),
            Text(input.RecipientName),
            Text(input.EventSummary),
            Text(input.ActionLabel),
            input.ExchangeUrl,
            "This is an account-related update for an exchange you organize or participate in.",
            input.RecipientUserId, input.Customization);
    }

    /// <summary>
    /// Produces both body alternatives after validating the address and action URL.
    /// </summary>
    private static TransactionalEmail Create(
        EmailCategory category,
        string eventId,
        string toAddress,
        string subject,
        string recipientName,
        string intro,
        string actionLabel,
        Uri actionUrl,
        string reason,
        string? recipientUserId = null,
        ExchangeCustomization? customization = null)
    {
        ValidateAddress(toAddress);
        ArgumentNullException.ThrowIfNull(actionUrl);
        if (!actionUrl.IsAbsoluteUri || actionUrl.Scheme is not ("https" or "http"))
            throw new ArgumentException("Email action URLs must be absolute HTTP URLs.", nameof(actionUrl));

        var safeRecipient = HtmlEncoder.Default.Encode(recipientName);
        var safeIntro = HtmlEncoder.Default.Encode(intro);
        var safeLabel = HtmlEncoder.Default.Encode(actionLabel);
        var safeUrl = HtmlEncoder.Default.Encode(actionUrl.AbsoluteUri);
        var safeReason = HtmlEncoder.Default.Encode(reason);
        // Said once, in the one place every template renders through, so no message can be written
        // without it. The From address is no-reply@humbugg.com and nobody reads it — telling people
        // where to write instead is the difference between a dead end and a support channel.
        var safeSupport = HtmlEncoder.Default.Encode(SupportLine);
        var primary = customization?.PrimaryColor is { Length: 7 } color && color[0] == '#' ? color : "#7C2D12";
        var customCopy = string.Join(" ", new[] { customization?.Greeting, customization?.Instructions }
            .Where(value => !string.IsNullOrWhiteSpace(value)).Select(value => Text(value!)));
        var safeCustomCopy = HtmlEncoder.Default.Encode(customCopy);
        var html = $$"""
            <!doctype html>
            <html lang="en">
              <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>{{HtmlEncoder.Default.Encode(subject)}}</title>
              </head>
              <body style="color:#1f2937">
                <main>
                  <h1><span style="color:{{primary}}">{{HtmlEncoder.Default.Encode(subject)}}</span></h1>
                  <p>Hello {{safeRecipient}},</p>
                  {{(safeCustomCopy.Length == 0 ? "" : $"<p>{safeCustomCopy}</p>")}}
                  <p>{{safeIntro}}</p>
                  <p><a href="{{safeUrl}}">{{safeLabel}}</a></p>
                  <p>{{safeReason}}</p>
                  <p>{{safeSupport}}</p>
                  <p>— Humbugg</p>
                </main>
              </body>
            </html>
            """;
        var text = $"{subject}\n\nHello {recipientName},\n\n{(customCopy.Length == 0 ? "" : customCopy + "\n\n")}{intro}\n\n{actionLabel}: {actionUrl.AbsoluteUri}\n\n{reason}\n\n{SupportLine}\n\n— Humbugg";

        return new TransactionalEmail(
            EmailMessageId.Create(category, eventId, toAddress),
            category,
            toAddress.Trim(),
            subject,
            html,
            text,
            string.IsNullOrWhiteSpace(recipientUserId) ? null : recipientUserId.Trim());
    }

    /// <summary>
    /// Where to write for help, and where not to.
    /// </summary>
    /// <remarks>
    /// Every Humbugg message is sent from <c>no-reply@humbugg.com</c>, which is a send-only SES
    /// identity — a reply to it goes nowhere and nobody is told. Naming the real inbox is what stops
    /// somebody's question disappearing into it. Inbound mail for support@ is Google Workspace; see
    /// docs/support-email.md.
    /// </remarks>
    internal const string SupportLine =
        "This address is not monitored. Email support@humbugg.com if you need help.";

    /// <summary>
    /// Normalizes user-controlled display text so it cannot inject email headers or lines.
    /// </summary>
    private static string Text(string value)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(value);
        return value.Replace('\r', ' ').Replace('\n', ' ').Trim();
    }

    /// <summary>Normalizes a subject using the same rules as other display text.</summary>
    private static string Subject(string value) => Text(value);

    /// <summary>Requires exactly one syntactically valid recipient address.</summary>
    private static void ValidateAddress(string value)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(value);
        var parsed = new MailAddress(value);
        if (!parsed.Address.Equals(value.Trim(), StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("A single email address is required.", nameof(value));
    }
}
