using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services.Email.Core;

namespace Humbugg.Api.Services;

/// <summary>
/// Anonymous questions between a giver and their recipient (#131).
/// </summary>
/// <remarks>
/// <para>
/// The giver may ask about a gift without saying who is asking. That is enforced by the schema
/// rather than by this class: no row stores a giver, so there is no field for a projection to leak,
/// no id for a URL to carry, and nothing for a later endpoint to expose by returning a whole record.
/// What this class contributes is the other half — every request re-derives who the giver is from
/// the draw, so authorization never needs the identity to be written down.
/// </para>
/// <para>
/// Both sides read the same shape. If the giver's view and the recipient's view were separate
/// projections, one of them would eventually differ by an identity; keeping them identical means a
/// leak would have to be visible in the one type both sides share.
/// </para>
/// </remarks>
public interface IQuestionService
{
    /// <summary>The giver's view of the conversation with the person they were assigned.</summary>
    Task<QuestionThread> GetForGiverAsync(string groupId, CancellationToken cancellationToken = default);

    /// <summary>The recipient's view of the conversation about their own list.</summary>
    Task<QuestionThread> GetForRecipientAsync(string groupId, CancellationToken cancellationToken = default);

    Task<QuestionThread> AskAsync(string groupId, SendQuestionRequest request, CancellationToken cancellationToken = default);
    Task<QuestionThread> ReplyAsync(string groupId, SendQuestionRequest request, CancellationToken cancellationToken = default);

    /// <summary>The recipient ends (or reopens) the conversation. The giver cannot.</summary>
    Task<QuestionThread> SetBlockedAsync(string groupId, BlockQuestionsRequest request, CancellationToken cancellationToken = default);
}

internal sealed class QuestionService(
    ICurrentUser user,
    IGroupRepository groups,
    IMembershipRepository memberships,
    IInvitationRepository invitations,
    IQuestionRepository questions,
    ITransactionalEmailService email,
    ITransactionalEmailTemplates templates,
    HumbuggSettings settings) : IQuestionService
{
    /// <summary>Plenty for clarifying a size or a colour; short of a chat product.</summary>
    internal const int MaxMessagesPerThread = 50;
    internal const int MaxBodyLength = 1_000;

    /// <summary>
    /// The gap one side must leave between its own messages.
    /// </summary>
    /// <remarks>
    /// Deliberately per SIDE and not per account: the limit has to hold without knowing who the
    /// giver is, and "this side last wrote at" is readable from the thread itself. It is a
    /// flood guard, not a throttle — a real conversation never notices thirty seconds.
    /// </remarks>
    internal static readonly TimeSpan MinimumGap = TimeSpan.FromSeconds(30);

    public async Task<QuestionThread> GetForGiverAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var context = await RequireGiverAsync(groupId, cancellationToken);
        return await ProjectAsync(context, QuestionAuthor.Giver, cancellationToken);
    }

    public async Task<QuestionThread> GetForRecipientAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var context = await RequireRecipientAsync(groupId, cancellationToken);
        return await ProjectAsync(context, QuestionAuthor.Recipient, cancellationToken);
    }

    public async Task<QuestionThread> AskAsync(
        string groupId,
        SendQuestionRequest request,
        CancellationToken cancellationToken = default) =>
        await SendAsync(await RequireGiverAsync(groupId, cancellationToken), QuestionAuthor.Giver, request, cancellationToken);

    public async Task<QuestionThread> ReplyAsync(
        string groupId,
        SendQuestionRequest request,
        CancellationToken cancellationToken = default) =>
        await SendAsync(await RequireRecipientAsync(groupId, cancellationToken), QuestionAuthor.Recipient, request, cancellationToken);

    public async Task<QuestionThread> SetBlockedAsync(
        string groupId,
        BlockQuestionsRequest request,
        CancellationToken cancellationToken = default)
    {
        // Only the recipient. A giver who could block would be able to end a conversation the other
        // side started, and a giver who could UNBLOCK would defeat the control entirely.
        var context = await RequireRecipientAsync(groupId, cancellationToken);
        await questions.SetBlockedAsync(
            new QuestionThreadRecord(
                context.ThreadId, groupId, context.RecipientMemberId, request.Blocked,
                DateTimeOffset.UtcNow.ToString("O")),
            cancellationToken);
        return await ProjectAsync(context, QuestionAuthor.Recipient, cancellationToken);
    }

    // ── Sending ─────────────────────────────────────────────────────────────────────────────────

    private async Task<QuestionThread> SendAsync(
        ThreadContext context,
        QuestionAuthor author,
        SendQuestionRequest request,
        CancellationToken cancellationToken)
    {
        var body = Body(request.Body);
        var (thread, messages) = await questions.GetThreadAsync(context.ThreadId, cancellationToken);

        // The recipient may still write on a thread they have blocked — blocking stops questions
        // arriving, not their own last word ("please stop asking", or an answer they still want to
        // give). Only the giver is refused.
        if (thread?.Blocked == true && author == QuestionAuthor.Giver)
            throw ApiException.Conflict(BlockedMessage(author));

        if (messages.Count >= MaxMessagesPerThread)
            throw ApiException.Conflict(
                $"This conversation has reached {MaxMessagesPerThread} messages. Carry on outside Humbugg.");

        var now = DateTimeOffset.UtcNow;
        var last = messages.LastOrDefault(message => message.Author == author);
        if (last is not null &&
            DateTimeOffset.TryParse(last.CreatedAt, System.Globalization.CultureInfo.InvariantCulture,
                System.Globalization.DateTimeStyles.RoundtripKind, out var lastAt) &&
            now - lastAt < MinimumGap)
            throw ApiException.Conflict(
                $"Give it {(int)MinimumGap.TotalSeconds} seconds between messages.");

        await questions.AppendAsync(
            new QuestionMessageRecord(
                context.ThreadId,
                MessageId(now),
                context.GroupId,
                context.DrawId,
                context.RecipientMemberId,
                author,
                body,
                now.ToString("O")),
            cancellationToken);

        await NotifyAsync(context, author, cancellationToken);
        return await ProjectAsync(context, author, cancellationToken);
    }

    /// <summary>
    /// A timestamp-prefixed id, so the sort key orders chronologically on its own.
    /// </summary>
    /// <remarks>
    /// The random suffix is a collision guard for two messages in the same tick, NOT a secret: it
    /// appears in the response either side already reads. Nothing about a message id is derived from
    /// who wrote it — an id that encoded the author would put the giver back into the schema through
    /// the one field both sides can see.
    /// </remarks>
    private static string MessageId(DateTimeOffset at) =>
        $"{at.UtcDateTime:yyyyMMddTHHmmss.fffffffZ}-{Guid.NewGuid():N}"[..40];

    // ── Notification ────────────────────────────────────────────────────────────────────────────

    /// <summary>
    /// Tells the other side that something arrived, and nothing else.
    /// </summary>
    /// <remarks>
    /// It never names either party and never carries the message body. A giver's notification that
    /// named their recipient would put the assignment in an inbox — the same reason
    /// <c>AssignmentAvailable</c> says Humbugg never puts a recipient's name in email — and a
    /// recipient's notification that named the asker would defeat the feature outright.
    ///
    /// Routed through <c>AccountExchangeEvent</c>, which carries the recipient's user id and so is
    /// suppressed for anyone who has turned non-essential mail off. A failure to send must not undo
    /// a message that is already stored, so this never throws.
    ///
    /// An address is only ever on file when the person joined through a managed invitation, which is
    /// a Plus capability — Humbugg stores no email on the profile, the access token carries one only
    /// for the caller, and neither is the other side of this conversation. So on a Free exchange
    /// this usually sends nothing, and that is the honest outcome rather than a gap: the app shows
    /// the thread either way, and inventing an address to notify is not available.
    /// </remarks>
    private async Task NotifyAsync(ThreadContext context, QuestionAuthor author, CancellationToken cancellationToken)
    {
        try
        {
            var toMemberId = author == QuestionAuthor.Giver ? context.RecipientMemberId : context.GiverMemberId;
            var member = await memberships.GetAsync(toMemberId, cancellationToken);
            if (member is null) return;
            var address = (await invitations.GetByGroupAsync(context.GroupId, cancellationToken))
                .Where(item => item.Status == "accepted" && item.AcceptedUserId == member.UserId)
                .OrderByDescending(item => item.AcceptedAt, StringComparer.Ordinal)
                .Select(item => item.Email)
                .FirstOrDefault();
            if (string.IsNullOrWhiteSpace(address)) return;

            var summary = author == QuestionAuthor.Giver
                ? "Someone in this exchange asked you a question about your gift. Humbugg does not say who."
                : "You have a reply to your anonymous question.";

            await email.SendAsync(
                templates.AccountExchangeEvent(new AccountExchangeEventEmail(
                    // One event id per message, so a retry is de-duplicated rather than re-sent.
                    $"question:{context.ThreadId}:{author}:{DateTimeOffset.UtcNow:yyyyMMddHHmm}",
                    address,
                    member.DisplayName,
                    context.GroupName,
                    summary,
                    "Open the exchange",
                    new Uri($"{settings.AppBaseUrl}/groups/{context.GroupId}"),
                    member.UserId)),
                cancellationToken);
        }
        catch
        {
            // The message is stored; a mail failure is not the sender's problem to see.
        }
    }

    // ── Authorization ───────────────────────────────────────────────────────────────────────────

    /// <summary>
    /// Everything a thread operation needs, resolved from the caller and the draw.
    /// </summary>
    /// <remarks>
    /// <see cref="GiverMemberId"/> lives here, in memory, for the length of one request — it is what
    /// the notification needs to find an address. It is never written to a row and never reaches a
    /// response.
    /// </remarks>
    private sealed record ThreadContext(
        string GroupId,
        string GroupName,
        string DrawId,
        string ThreadId,
        string RecipientMemberId,
        string GiverMemberId);

    private async Task<ThreadContext> RequireGiverAsync(string groupId, CancellationToken cancellationToken)
    {
        var (group, membership, draw) = await RequireDrawnMembershipAsync(groupId, cancellationToken);
        if (!draw.Assignments.TryGetValue(membership.MemberId, out var recipientId))
            throw ApiException.NotFound("You do not have an assignment in this draw.");
        return Context(group, draw, recipientId, membership.MemberId);
    }

    private async Task<ThreadContext> RequireRecipientAsync(string groupId, CancellationToken cancellationToken)
    {
        var (group, membership, draw) = await RequireDrawnMembershipAsync(groupId, cancellationToken);
        // Who gives to me — found by inverting the draw, and used only to address a notification.
        var giverId = draw.Assignments.FirstOrDefault(pair => pair.Value == membership.MemberId).Key;
        if (string.IsNullOrEmpty(giverId))
            throw ApiException.NotFound("Nobody is assigned to you in this draw.");
        return Context(group, draw, membership.MemberId, giverId);
    }

    private static ThreadContext Context(GroupRecord group, DrawRecord draw, string recipientId, string giverId) =>
        new(group.GroupId, group.Name, draw.DrawId,
            QuestionRepository.ThreadId(group.GroupId, draw.DrawId, recipientId), recipientId, giverId);

    private async Task<(GroupRecord Group, MembershipRecord Membership, DrawRecord Draw)> RequireDrawnMembershipAsync(
        string groupId,
        CancellationToken cancellationToken)
    {
        var group = await groups.GetAsync(groupId, cancellationToken)
            ?? throw ApiException.NotFound("Group not found.");
        var membership = await memberships.GetByUserAndGroupAsync(user.UserId, groupId, cancellationToken)
            ?? throw ApiException.Forbidden("You are not a member of this group.");
        if (group.Status != GroupStatus.Drawn)
            throw ApiException.Conflict("Questions open once the exchange has been drawn.");
        if (!membership.IsParticipating)
            throw ApiException.Forbidden("Only participants in the draw can use questions.");
        var draw = await groups.GetDrawAsync(groupId, cancellationToken)
            ?? throw ApiException.NotFound("This exchange has no draw.");
        return (group, membership, draw);
    }

    // ── Projection ──────────────────────────────────────────────────────────────────────────────

    private async Task<QuestionThread> ProjectAsync(
        ThreadContext context,
        QuestionAuthor viewer,
        CancellationToken cancellationToken)
    {
        var (thread, messages) = await questions.GetThreadAsync(context.ThreadId, cancellationToken);
        var blocked = thread?.Blocked == true;
        var full = messages.Count >= MaxMessagesPerThread;
        var canSend = !full && !(blocked && viewer == QuestionAuthor.Giver);
        return new QuestionThread(
            // Author is the SIDE. This is the only thing either party learns about who wrote a
            // message, and it is the same value for both viewers.
            messages.Select(message => new QuestionMessage(
                message.MessageId, message.Author, message.Body, message.CreatedAt)).ToList(),
            blocked,
            canSend,
            canSend ? null : full
                ? $"This conversation has reached {MaxMessagesPerThread} messages."
                : BlockedMessage(viewer),
            MaxMessagesPerThread);
    }

    private static string BlockedMessage(QuestionAuthor viewer) => viewer == QuestionAuthor.Giver
        // Says the door is shut without saying who shut it or when — a "they blocked you at 14:02"
        // is a fact about the recipient's behaviour that the giver has no need for.
        ? "Questions are turned off for this gift."
        : "You have turned questions off. Turn them back on to hear from your giver.";

    private static string Body(string? value)
    {
        var trimmed = (value ?? "").Trim();
        if (trimmed.Length == 0) throw ApiException.BadRequest("A question cannot be empty.");
        if (trimmed.Length > MaxBodyLength)
            throw ApiException.BadRequest($"Keep it under {MaxBodyLength} characters.");
        // Plain text, and stored plain: control characters other than a newline are stripped so the
        // stored body cannot carry terminal escapes or bidirectional overrides into whatever renders
        // it next. The app renders it as text and the email never includes it at all.
        var cleaned = new string(trimmed
            .Where(character => character == '\n' || !char.IsControl(character))
            .ToArray());
        if (cleaned.Trim().Length == 0) throw ApiException.BadRequest("A question cannot be empty.");
        return cleaned;
    }
}
