using System.Text.Json;
using Humbugg.Api;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Humbugg.Api.Services.Email.Core;
using Xunit;

namespace Humbugg.Api.Tests;

/// <summary>
/// Anonymous questions (#131).
/// </summary>
/// <remarks>
/// The feature is a two-person thread; the thing worth testing is the one guarantee — that neither
/// side learns who the giver is. The issue names five surfaces it could leak through (UI, API
/// payloads, notifications, URLs, metadata) and this file attacks four of them directly. The fifth,
/// the UI, cannot leak what the payload does not carry, and the app's own tests cover the rendering.
/// </remarks>
public sealed class QuestionServiceTests
{
    private const string Ana = "ana";     // gives to Bo
    private const string Bo = "bo";       // gives to Ana
    private const string Group = "group";

    // ── The guarantee ───────────────────────────────────────────────────────────────────────────

    /// <summary>
    /// The strongest form of the test: not "the response omitted the giver" but "no row has one".
    /// </summary>
    /// <remarks>
    /// A projection test would only pin today's endpoints. Serialising every stored row and
    /// searching it for either member id pins the schema, which is what the anonymity actually rests
    /// on — a field that does not exist cannot be returned by an endpoint written next year.
    /// </remarks>
    [Fact]
    public async Task NoStoredRowCarriesTheGiver()
    {
        var world = World();
        await world.AsAna.AskAsync(Group, new SendQuestionRequest("Which size?"), Token);
        await world.AsBo.ReplyAsync(Group, new SendQuestionRequest("Medium, thanks."), Token);

        var stored = JsonSerializer.Serialize(world.Questions.All);

        // Bo is the recipient and is named — the thread is keyed by whose list it is, which is not a
        // secret from anybody. Ana is the giver, and appears nowhere.
        Assert.Contains(Bo, stored, StringComparison.Ordinal);
        Assert.DoesNotContain(Ana, stored, StringComparison.Ordinal);
    }

    /// <summary>
    /// Both sides read the identical payload, and it names a SIDE rather than a person.
    /// </summary>
    [Fact]
    public async Task BothSidesSeeTheSameThreadAndOnlyEverASide()
    {
        var world = World();
        await world.AsAna.AskAsync(Group, new SendQuestionRequest("Which size?"), Token);
        await world.AsBo.ReplyAsync(Group, new SendQuestionRequest("Medium, thanks."), Token);

        var giverView = await world.AsAna.GetForGiverAsync(Group, Token);
        var recipientView = await world.AsBo.GetForRecipientAsync(Group, Token);

        Assert.Equal(
            giverView.Messages.Select(message => (message.Author, message.Body, message.MessageId)),
            recipientView.Messages.Select(message => (message.Author, message.Body, message.MessageId)));
        Assert.Equal([QuestionAuthor.Giver, QuestionAuthor.Recipient],
            recipientView.Messages.Select(message => message.Author));
        Assert.DoesNotContain(Ana, JsonSerializer.Serialize(recipientView), StringComparison.Ordinal);
    }

    /// <summary>
    /// A message id is a timestamp and a random suffix — never anything derived from its author.
    /// </summary>
    /// <remarks>
    /// Both sides read every message id, so an id that encoded who wrote it would hand the recipient
    /// the giver through the one field the payload cannot omit.
    /// </remarks>
    [Fact]
    public async Task MessageIdsCarryNothingAboutWhoWroteThem()
    {
        var world = World();
        await world.AsAna.AskAsync(Group, new SendQuestionRequest("Which size?"), Token);
        await world.AsBo.ReplyAsync(Group, new SendQuestionRequest("Medium."), Token);

        var ids = world.Questions.All.Select(message => message.MessageId).ToList();
        Assert.All(ids, id =>
        {
            Assert.DoesNotContain(Ana, id, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain(Bo, id, StringComparison.OrdinalIgnoreCase);
        });
        // Chronological on their own, so the sort key needs no second attribute.
        Assert.Equal(ids.OrderBy(id => id, StringComparer.Ordinal), ids);
    }

    /// <summary>
    /// The notification says something arrived and nothing else.
    /// </summary>
    /// <remarks>
    /// A recipient's mail naming the asker would defeat the feature; a giver's mail naming the
    /// recipient would put the draw assignment in an inbox, which is the same reason
    /// <c>AssignmentAvailable</c> refuses to carry a name. Neither may carry the body either — mail
    /// is the least private surface Humbugg has.
    /// </remarks>
    [Fact]
    public async Task NotificationsNameNobodyAndQuoteNothing()
    {
        var world = World(withAddresses: true);
        await world.AsAna.AskAsync(Group, new SendQuestionRequest("Is the blue one still right?"), Token);
        await world.AsBo.ReplyAsync(Group, new SendQuestionRequest("Yes, blue."), Token);

        Assert.Equal(2, world.Email.Sent.Count);
        var toRecipient = world.Email.Sent.Single(message => message.ToAddress == "bo@example.test");
        var toGiver = world.Email.Sent.Single(message => message.ToAddress == "ana@example.test");

        // Each mail may greet the person it is addressed to. What it may not do is name the OTHER
        // party — that is the assignment, in an inbox — or quote a word of the conversation.
        Assert.DoesNotContain("Ana", Whole(toRecipient), StringComparison.Ordinal);
        Assert.DoesNotContain("Bo", Whole(toGiver), StringComparison.Ordinal);
        Assert.All([toRecipient, toGiver], message =>
            Assert.DoesNotContain("blue", Whole(message), StringComparison.OrdinalIgnoreCase));

        Assert.Contains("does not say who", toRecipient.TextBody, StringComparison.Ordinal);
        // Both are routed through the account-event category, which carries the reader's user id and
        // so is dropped for anyone who has turned non-essential mail off.
        Assert.All([toRecipient, toGiver], message => Assert.NotNull(message.RecipientUserId));
    }

    /// <summary>
    /// A mail failure never costs a message that is already stored.
    /// </summary>
    [Fact]
    public async Task AMessageSurvivesAFailedNotification()
    {
        var world = World(withAddresses: true);
        world.Email.Throw = true;

        var thread = await world.AsAna.AskAsync(Group, new SendQuestionRequest("Which size?"), Token);

        Assert.Single(thread.Messages);
        Assert.Single(world.Questions.All);
    }

    // ── Authorization ───────────────────────────────────────────────────────────────────────────

    [Fact]
    public async Task OnlyAParticipantWithACurrentAssignmentCanOpenAThread()
    {
        var undrawn = World(drawn: false);
        Assert.Equal(409, (await Assert.ThrowsAsync<ApiException>(() =>
            undrawn.AsAna.AskAsync(Group, new SendQuestionRequest("Hello"), Token))).StatusCode);

        // A member of the group who is sitting out has no assignment and no thread.
        var world = World(sittingOut: true);
        Assert.Equal(403, (await Assert.ThrowsAsync<ApiException>(() =>
            world.AsAna.AskAsync(Group, new SendQuestionRequest("Hello"), Token))).StatusCode);

        // And a stranger is not a member at all.
        var stranger = World().For("nobody");
        Assert.Equal(403, (await Assert.ThrowsAsync<ApiException>(() =>
            stranger.AskAsync(Group, new SendQuestionRequest("Hello"), Token))).StatusCode);
    }

    /// <summary>
    /// An organizer has no way in. There is no organizer route, and being one changes nothing:
    /// the only threads reachable are the two the caller is personally party to.
    /// </summary>
    [Fact]
    public async Task AnOrganizerReadsOnlyTheirOwnTwoSides()
    {
        var world = World(organizer: Ana);
        await world.AsBo.AskAsync(Group, new SendQuestionRequest("A question for Ana."), Token);

        // Ana organizes, and reads the thread about her own list — as its recipient, like anyone.
        var mine = await world.AsAna.GetForRecipientAsync(Group, Token);
        Assert.Single(mine.Messages);

        // The thread she is the GIVER on is Bo's, and it is empty. Nothing about organizing opens a
        // third door: with two participants there are exactly two threads and she is party to both.
        var theirs = await world.AsAna.GetForGiverAsync(Group, Token);
        Assert.Empty(theirs.Messages);
    }

    // ── Blocking ────────────────────────────────────────────────────────────────────────────────

    [Fact]
    public async Task TheRecipientCanEndTheConversationAndReopenIt()
    {
        var world = World();
        await world.AsAna.AskAsync(Group, new SendQuestionRequest("Which size?"), Token);

        var blocked = await world.AsBo.SetBlockedAsync(Group, new BlockQuestionsRequest(true), Token);
        Assert.True(blocked.Blocked);

        var refused = await Assert.ThrowsAsync<ApiException>(() =>
            world.AsAna.AskAsync(Group, new SendQuestionRequest("Still there?"), Token));
        Assert.Equal(409, refused.StatusCode);
        // Says the door is shut, not who shut it or when.
        Assert.DoesNotContain("Bo", refused.Message, StringComparison.OrdinalIgnoreCase);

        var giverView = await world.AsAna.GetForGiverAsync(Group, Token);
        Assert.False(giverView.CanSend);

        await world.AsBo.SetBlockedAsync(Group, new BlockQuestionsRequest(false), Token);
        Assert.True((await world.AsAna.GetForGiverAsync(Group, Token)).CanSend);
    }

    /// <summary>
    /// The recipient keeps their own last word on a thread they have ended.
    /// </summary>
    /// <remarks>
    /// Blocking stops questions arriving; it is not a gag on the person who pressed it. "Please stop
    /// asking" and a final answer are both things they may still want to send.
    /// </remarks>
    [Fact]
    public async Task BlockingDoesNotSilenceTheRecipient()
    {
        var world = World();
        await world.AsBo.SetBlockedAsync(Group, new BlockQuestionsRequest(true), Token);

        var thread = await world.AsBo.ReplyAsync(Group, new SendQuestionRequest("It is a surprise, thanks."), Token);

        Assert.Single(thread.Messages);
        Assert.True(thread.Blocked);
    }

    [Fact]
    public async Task AGiverCannotBlockOrUnblock()
    {
        var world = World();
        // There is no giver route for it, and the service resolves the caller as the recipient — so
        // Ana blocking sets the flag on HER OWN thread (Bo's questions to her), never on Bo's.
        await world.AsAna.SetBlockedAsync(Group, new BlockQuestionsRequest(true), Token);

        Assert.True((await world.AsAna.GetForRecipientAsync(Group, Token)).Blocked);
        Assert.False((await world.AsBo.GetForRecipientAsync(Group, Token)).Blocked);
        Assert.True((await world.AsAna.GetForGiverAsync(Group, Token)).CanSend);
    }

    // ── Limits and content ──────────────────────────────────────────────────────────────────────

    [Fact]
    public async Task BodiesAreCheckedForLengthAndEmptiness()
    {
        var world = World();
        foreach (var bad in new[] { "", "   ", " " })
            Assert.Equal(400, (await Assert.ThrowsAsync<ApiException>(() =>
                world.AsAna.AskAsync(Group, new SendQuestionRequest(bad), Token))).StatusCode);

        Assert.Equal(400, (await Assert.ThrowsAsync<ApiException>(() => world.AsAna.AskAsync(
            Group, new SendQuestionRequest(new string('x', QuestionService.MaxBodyLength + 1)), Token))).StatusCode);
    }

    /// <summary>
    /// Control characters are stripped rather than stored, and a newline is kept.
    /// </summary>
    [Fact]
    public async Task ControlCharactersAreStrippedAndNewlinesKept()
    {
        var world = World();
        await world.AsAna.AskAsync(Group, new SendQuestionRequest("Blue or\ngreen?"), Token);

        Assert.Equal("Blue or\ngreen?", world.Questions.All.Single().Body);
    }

    [Fact]
    public async Task OneSideCannotFloodTheThread()
    {
        var world = World();
        await world.AsAna.AskAsync(Group, new SendQuestionRequest("Which size?"), Token);

        var tooSoon = await Assert.ThrowsAsync<ApiException>(() =>
            world.AsAna.AskAsync(Group, new SendQuestionRequest("Hello?"), Token));
        Assert.Equal(409, tooSoon.StatusCode);

        // The gap is per SIDE, so the reply is not held up by the question.
        var replied = await world.AsBo.ReplyAsync(Group, new SendQuestionRequest("Medium."), Token);
        Assert.Equal(2, replied.Messages.Count);
    }

    [Fact]
    public async Task AThreadStopsAtItsMessageLimit()
    {
        var world = World();
        var stale = DateTimeOffset.UtcNow.AddHours(-1).ToString("O");
        for (var index = 0; index < QuestionService.MaxMessagesPerThread; index++)
            await world.Questions.AppendAsync(new QuestionMessageRecord(
                QuestionRepository.ThreadId(Group, "draw-1", Bo),
                $"seed-{index:D3}", Group, "draw-1", Bo, QuestionAuthor.Giver, "filler", stale), Token);

        var error = await Assert.ThrowsAsync<ApiException>(() =>
            world.AsAna.AskAsync(Group, new SendQuestionRequest("One more"), Token));
        Assert.Equal(409, error.StatusCode);
        Assert.False((await world.AsAna.GetForGiverAsync(Group, Token)).CanSend);
    }

    // ── Draw lifecycle ──────────────────────────────────────────────────────────────────────────

    /// <summary>
    /// A reset ends the conversation, because after it you may be buying for somebody else.
    /// </summary>
    /// <remarks>
    /// The thread id contains the draw id, so a new draw is a new, empty thread and the old one is
    /// unreachable by every route at once — the same self-invalidation the assignment-viewed flag
    /// and the purchase claims use, for the same reason.
    /// </remarks>
    [Fact]
    public async Task ANewDrawStartsAnEmptyConversation()
    {
        var world = World();
        await world.AsAna.AskAsync(Group, new SendQuestionRequest("Which size?"), Token);
        Assert.Single((await world.AsBo.GetForRecipientAsync(Group, Token)).Messages);

        world.Groups.Redraw("draw-2");

        Assert.Empty((await world.AsBo.GetForRecipientAsync(Group, Token)).Messages);
        Assert.Empty((await world.AsAna.GetForGiverAsync(Group, Token)).Messages);
    }

    // ── Harness ─────────────────────────────────────────────────────────────────────────────────

    private static string Whole(TransactionalEmail message) =>
        $"{message.Subject} {message.HtmlBody} {message.TextBody}";

    private static CancellationToken Token => TestContext.Current.CancellationToken;

    private sealed class Exchange
    {
        public FakeQuestions Questions { get; } = new();
        public DrawableGroups Groups { get; }
        public RecordingEmail Email { get; } = new();
        private readonly FakeMembers members;
        private readonly FakeInvitations invitations;

        public Exchange(DrawableGroups groups, FakeMembers members, FakeInvitations invitations)
        {
            Groups = groups;
            this.members = members;
            this.invitations = invitations;
        }

        public IQuestionService For(string userId) => new QuestionService(
            new StubUser(userId), Groups, members, invitations, Questions, Email,
            new TransactionalEmailTemplates(),
            new HumbuggSettings(
                "us-east-1", "us-east-1", "pool", "client", ["http://localhost:5173"],
                "http://localhost:5173", null, "profiles", "groups", "members", "draws", "audit", "analytics"));

        public IQuestionService AsAna => For($"user-{Ana}");
        public IQuestionService AsBo => For($"user-{Bo}");
    }

    private static Exchange World(
        bool drawn = true,
        bool withAddresses = false,
        bool sittingOut = false,
        string? organizer = null)
    {
        var members = new FakeMembers(
            [Member(Ana, organizer == Ana, participating: !sittingOut), Member(Bo, organizer == Bo)]);
        var invitations = new FakeInvitations();
        if (withAddresses)
            foreach (var id in new[] { Ana, Bo })
                invitations.Items.Add(new InvitationRecord(
                    $"inv-{id}", Group, $"{id}@example.test", "hash", "accepted",
                    "2099-01-01T00:00:00Z", "now", "now", AcceptedAt: "now", AcceptedUserId: $"user-{id}"));
        return new Exchange(new DrawableGroups(drawn), members, invitations);
    }

    private static MembershipRecord Member(string id, bool organizer, bool participating = true) => new(
        id, Group, $"user-{id}", id == Ana ? "Ana" : "Bo", organizer, participating,
        "wish", "avoid", new Address("address"), "now", "now");

    private sealed class StubUser(string userId) : ICurrentUser
    {
        public string UserId => userId;
    }

    /// <summary>A group repository whose draw can be replaced, for the reset case.</summary>
    private sealed class DrawableGroups(bool drawn) : IGroupRepository
    {
        private DrawRecord? draw = drawn
            ? new(Group, "draw-1", new Dictionary<string, string> { [Ana] = Bo, [Bo] = Ana }, "now", "user-ana")
            : null;

        public void Redraw(string drawId) => draw = draw is null
            ? null
            : draw with { DrawId = drawId };

        public Task<GroupRecord?> GetAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<GroupRecord?>(new(
                Group, "user-ana", "Exchange", "", null, null, null, "USD", PlanCode.Free, null,
                draw is null ? GroupStatus.Open : GroupStatus.Drawn, "hash", [], "now", "now"));

        public Task<DrawRecord?> GetDrawAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult(draw);

        public Task<GroupRecord> CreateAsync(GroupRecord value, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<GroupRecord> UpdateAsync(string groupId, IReadOnlyDictionary<string, Amazon.DynamoDBv2.Model.AttributeValue> fields, GroupStatus? expectedStatus = null, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task CreateDrawAsync(string groupId, IReadOnlyDictionary<string, string> assignments, string actorUserId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task ResetDrawAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class FakeMembers(IEnumerable<MembershipRecord> seed) : IMembershipRepository
    {
        public List<MembershipRecord> Items { get; } = seed.ToList();

        public Task<MembershipRecord?> GetAsync(string memberId, CancellationToken cancellationToken = default) =>
            Task.FromResult(Items.FirstOrDefault(item => item.MemberId == memberId));
        public Task<MembershipRecord?> GetByUserAndGroupAsync(string userId, string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult(Items.FirstOrDefault(item => item.UserId == userId && item.GroupId == groupId));
        public Task<IReadOnlyList<MembershipRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<MembershipRecord>>(Items.Where(item => item.GroupId == groupId).ToList());
        public Task<IReadOnlyList<MembershipRecord>> GetByUserAsync(string userId, CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<MembershipRecord>>(Items.Where(item => item.UserId == userId).ToList());
        public Task<MembershipRecord> CreateAsync(string groupId, string userId, string displayName, bool organizer, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdatePrivateAsync(string memberId, string wishlist, string avoidances, Address address, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdateParticipationAsync(string memberId, bool participating, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdateOrganizerAsync(string memberId, bool organizer, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task MarkAssignmentViewedAsync(string memberId, string drawId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task SetGiftStageAsync(string memberId, string drawId, GiftStage stage, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
        public Task SetGiftReceivedAsync(string memberId, string drawId, bool received, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
        public Task ClearGiftProgressAsync(string memberId, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
        public Task SetWishClaimAsync(string memberId, string drawId, string wishId, WishClaimRecord claim, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task RemoveWishClaimAsync(string memberId, string drawId, string wishId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task ClearWishClaimsAsync(string memberId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task AnonymizeAsync(string memberId, string pseudonym, string displayName, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string memberId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class RecordingEmail : ITransactionalEmailService
    {
        public List<TransactionalEmail> Sent { get; } = [];
        public bool Throw { get; set; }

        public Task<EmailSendResult> SendAsync(TransactionalEmail email, CancellationToken cancellationToken = default)
        {
            if (Throw) throw new InvalidOperationException("mail is down");
            Sent.Add(email);
            return Task.FromResult(new EmailSendResult(email.MessageId, email.Category, false, false, email.MessageId));
        }
    }
}
