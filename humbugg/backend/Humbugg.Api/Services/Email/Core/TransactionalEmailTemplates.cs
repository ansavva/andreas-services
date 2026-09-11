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
/// <remarks>
/// <para>
/// <b>One frame, every email.</b> Everything renders through <see cref="Create"/>: the brand row (the
/// green H tile the app uses as its icon, built from a table cell so no client can block it, and
/// the wordmark in Lily Script One), a cream card with an eyebrow, a headline, the body, the
/// organizer's own words when there are any, one button, and a muted footer that says why the
/// message came and where to write. Colours are Humbugg's brand tokens
/// (<c>app/src/theme/brand-colors.json</c>) written inline, because email has no stylesheet; the
/// one text family is Open Sans with an Arial fallback, as the app has been since #637. Tables
/// and inline styles rather than anything modern, because Gmail and Outlook are the audience.
/// </para>
/// <para>
/// <b>The organizer's words are content, not chrome.</b> Until #677 an exchange carried a colour
/// that became the heading colour of every email about it; now the greeting and instructions
/// appear as a quoted block inside Humbugg's frame, attributed to the organizer. Humbugg's frame
/// is Humbugg's.
/// </para>
/// <para>
/// <b>Nothing typed by a person reaches the HTML unencoded.</b> Every slot goes through
/// <see cref="HtmlEncoder"/>; <see cref="Text"/> strips line breaks so nothing can inject a header
/// into the plain-text part or a subject. The server refused HTML and links in the greeting and
/// instructions before they were stored, and this encodes them anyway.
/// </para>
/// </remarks>
internal sealed class TransactionalEmailTemplates : ITransactionalEmailTemplates
{
    /// <inheritdoc />
    public TransactionalEmail Invitation(InvitationEmail input)
    {
        ArgumentNullException.ThrowIfNull(input);
        var organizer = Text(input.OrganizerName);
        var exchange = Text(input.ExchangeName);
        return Create(
            EmailCategory.Invitation,
            input.EventId,
            input.ToAddress,
            Subject($"{organizer} invited you to {exchange}"),
            "You're invited",
            input.RecipientName,
            $"{organizer} is running a gift exchange on Humbugg and would like you in it. " +
            "Follow the link, sign in, and add a few things you'd love — Humbugg keeps the surprise safe until draw day.",
            "View your invitation",
            input.InvitationUrl,
            "This link is yours alone: it signs you into this exchange and nobody else's.",
            $"You're receiving this because {organizer} invited {Text(input.ToAddress)} to an exchange on Humbugg.",
            customization: input.Customization,
            attribution: organizer);
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
            Subject($"{exchange}: a reminder"),
            "Reminder",
            input.RecipientName,
            Text(input.Reminder),
            "Open the exchange",
            input.ExchangeUrl,
            null,
            $"You're receiving this because {exchange} on Humbugg has reminders turned on.",
            input.RecipientUserId,
            input.Customization);
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
            "Draw day",
            input.RecipientName,
            $"Names have been drawn for {exchange}. Your recipient is waiting for you — sign in to see who, privately.",
            "See who you drew",
            input.ExchangeUrl,
            "Only you can see your assignment, and only after signing in. It is never in an email.",
            $"You're receiving this because you're part of {exchange} on Humbugg.",
            customization: input.Customization);
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
            Subject($"Your assignment for {exchange} is ready"),
            "Your assignment",
            input.RecipientName,
            $"Your private assignment for {exchange} is ready to view.",
            "View your assignment",
            input.AssignmentUrl,
            "Humbugg never puts the recipient's name in an email. Sign in to reveal it privately.",
            $"You're receiving this because you're part of {exchange} on Humbugg.",
            customization: input.Customization);
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
            "Update",
            input.RecipientName,
            Text(input.EventSummary),
            Text(input.ActionLabel),
            input.ExchangeUrl,
            null,
            $"You're receiving this because you organize or take part in {exchange} on Humbugg.",
            input.RecipientUserId,
            input.Customization);
    }

    // Brand tokens, from app/src/theme/brand-colors.json. Inline because email has no stylesheet;
    // named so a change there is a one-line change here.
    private const string Bg = "#fbf8ef";
    private const string Card = "#fffdf8";
    private const string SurfaceAlt = "#f1ecdf";
    private const string Ink = "#18332b";
    private const string Muted = "#626e67";
    private const string Line = "#ddd6c5";
    private const string Brand = "#1d5545";
    private const string Sans = "'Open Sans',Arial,Helvetica,sans-serif";
    private const string Script = "'Lily Script One',Georgia,'Times New Roman',serif";

    /// <summary>
    /// Produces both body alternatives after validating the address and action URL.
    /// </summary>
    /// <param name="eyebrow">The small-caps label above the headline — what kind of message this is.</param>
    /// <param name="recipientName">Who it is to; empty when only an address is known, and then the greeting is just "Hello,".</param>
    /// <param name="note">A muted line under the button about the link itself, or null.</param>
    /// <param name="why">The footer's "you're receiving this because…" sentence.</param>
    /// <param name="attribution">Who the organizer's words are from, when the message has one to name.</param>
    private static TransactionalEmail Create(
        EmailCategory category,
        string eventId,
        string toAddress,
        string subject,
        string eyebrow,
        string recipientName,
        string intro,
        string actionLabel,
        Uri actionUrl,
        string? note,
        string why,
        string? recipientUserId = null,
        ExchangeCustomization? customization = null,
        string? attribution = null)
    {
        ValidateAddress(toAddress);
        ArgumentNullException.ThrowIfNull(actionUrl);
        if (!actionUrl.IsAbsoluteUri || actionUrl.Scheme is not ("https" or "http"))
            throw new ArgumentException("Email action URLs must be absolute HTTP URLs.", nameof(actionUrl));

        var recipient = string.IsNullOrWhiteSpace(recipientName) ? "" : Text(recipientName);
        var greeting = customization?.Greeting is { } g && !string.IsNullOrWhiteSpace(g) ? Text(g) : "";
        var instructions = customization?.Instructions is { } i && !string.IsNullOrWhiteSpace(i) ? Text(i) : "";
        var hasWords = greeting.Length > 0 || instructions.Length > 0;

        string E(string value) => HtmlEncoder.Default.Encode(value);
        var safeUrl = E(actionUrl.AbsoluteUri);
        var hello = recipient.Length == 0 ? "Hello," : $"Hello {E(recipient)},";

        var words = !hasWords ? "" : $$"""
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 28px 0;">
                      <tr>
                        <td style="background-color:{{SurfaceAlt}};border-left:4px solid {{Brand}};border-radius:0 12px 12px 0;padding:16px 20px;">
                          {{(greeting.Length == 0 ? "" : $"<p style=\"margin:0 0 6px 0;font-family:{Sans};font-size:17px;line-height:26px;color:{Ink};font-weight:600;\">{E(greeting)}</p>")}}
                          {{(instructions.Length == 0 ? "" : $"<p style=\"margin:0;font-family:{Sans};font-size:15px;line-height:24px;color:{Ink};\">{E(instructions)}</p>")}}
                          {{(string.IsNullOrWhiteSpace(attribution) ? "" : $"<p style=\"margin:10px 0 0 0;font-family:{Sans};font-size:12px;line-height:16px;color:{Muted};\">— {E(Text(attribution))}</p>")}}
                        </td>
                      </tr>
                    </table>
        """;

        var html = $$"""
            <!doctype html>
            <html lang="en">
              <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <meta name="color-scheme" content="light">
                <meta name="supported-color-schemes" content="light">
                <title>{{E(subject)}}</title>
                <link href="https://fonts.googleapis.com/css2?family=Lily+Script+One&family=Open+Sans:wght@400;600;700&display=swap" rel="stylesheet">
              </head>
              <body style="margin:0;padding:0;background-color:{{Bg}};">
                <main>
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{{Bg}};">
                  <tr>
                    <td align="center" style="padding:32px 16px;">
                      <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;">
                        <tr>
                          <td style="padding:0 8px 20px 8px;">
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                              <tr>
                                <td width="40" height="40" align="center" valign="middle" style="width:40px;height:40px;background-color:{{Brand}};border-radius:10px;font-family:{{Script}};font-size:26px;line-height:40px;color:{{Card}};">H</td>
                                <td style="padding-left:12px;font-family:{{Script}};font-size:30px;line-height:40px;color:{{Brand}};letter-spacing:-0.01em;">Humbugg</td>
                              </tr>
                            </table>
                          </td>
                        </tr>
                        <tr>
                          <td style="background-color:{{Card}};border:1px solid {{Line}};border-radius:16px;padding:40px 40px 32px 40px;">
                            <p style="margin:0 0 12px 0;font-family:{{Sans}};font-size:12px;line-height:16px;letter-spacing:0.14em;text-transform:uppercase;color:{{Muted}};font-weight:600;">{{E(eyebrow)}}</p>
                            <h1 style="margin:0 0 20px 0;font-family:{{Sans}};font-weight:700;font-size:28px;line-height:36px;letter-spacing:-0.01em;color:{{Ink}};">{{E(subject)}}</h1>
                            <p style="margin:0 0 16px 0;font-family:{{Sans}};font-size:16px;line-height:26px;color:{{Ink}};">{{hello}}</p>
                            <p style="margin:0 0 24px 0;font-family:{{Sans}};font-size:16px;line-height:26px;color:{{Ink}};">{{E(intro)}}</p>
            {{words}}
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 {{(note is null ? "8" : "28")}}px 0;">
                              <tr>
                                <td align="center" style="background-color:{{Brand}};border-radius:12px;">
                                  <a href="{{safeUrl}}" style="display:inline-block;padding:14px 28px;font-family:{{Sans}};font-size:16px;line-height:20px;font-weight:600;color:{{Card}};text-decoration:none;border-radius:12px;">{{E(actionLabel)}}</a>
                                </td>
                              </tr>
                            </table>
                            {{(note is null ? "" : $"<p style=\"margin:0;font-family:{Sans};font-size:13px;line-height:20px;color:{Muted};\">{E(note)}</p>")}}
                          </td>
                        </tr>
                        <tr>
                          <td style="padding:24px 8px 0 8px;">
                            <p style="margin:0 0 6px 0;font-family:{{Sans}};font-size:12px;line-height:18px;color:{{Muted}};">{{E(why)}}</p>
                            <p style="margin:0;font-family:{{Sans}};font-size:12px;line-height:18px;color:{{Muted}};">This address is not monitored. Email <a href="mailto:support@humbugg.com" style="color:{{Brand}};text-decoration:underline;">support@humbugg.com</a> if you need help.</p>
                            <p style="margin:14px 0 0 0;font-family:{{Script}};font-size:18px;line-height:24px;color:{{Brand}};">Humbugg</p>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                </table>
                </main>
              </body>
            </html>
            """;

        var textWords = !hasWords ? "" :
            string.Join("\n", new[] { greeting, instructions, string.IsNullOrWhiteSpace(attribution) ? "" : $"— {Text(attribution)}" }
                .Where(line => line.Length > 0)) + "\n\n";
        var text =
            $"{subject}\n\n" +
            $"{(recipient.Length == 0 ? "Hello," : $"Hello {recipient},")}\n\n" +
            $"{intro}\n\n" +
            textWords +
            $"{actionLabel}: {actionUrl.AbsoluteUri}\n\n" +
            $"{(note is null ? "" : note + "\n\n")}" +
            $"{why}\n{SupportLine}\n\n— Humbugg";

        return new TransactionalEmail(
            EmailMessageId.Create(category, eventId, toAddress),
            category,
            toAddress.Trim(),
            subject,
            html,
            text,
            string.IsNullOrWhiteSpace(recipientUserId) ? null : recipientUserId.Trim());
    }

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
