using Humbugg.Api;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Humbugg.Api.Services.Email.Adapters.Memory;
using Humbugg.Api.Services.Email.Core;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class EmailPreferenceTests
{
    private static readonly Uri ActionUrl = new("https://humbugg.com/app/groups/group-1");
    private static readonly ITransactionalEmailTemplates Templates = new TransactionalEmailTemplates();

    [Theory]
    [InlineData(EmailCategory.Invitation, true)]
    [InlineData(EmailCategory.DrawCompleted, true)]
    [InlineData(EmailCategory.AssignmentAvailable, true)]
    [InlineData(EmailCategory.Reminder, false)]
    [InlineData(EmailCategory.AccountExchangeEvent, false)]
    public void ClassificationMatchesTheDecidedPolicy(EmailCategory category, bool essential)
    {
        Assert.Equal(essential, EmailClassification.IsEssential(category));
        Assert.Equal(
            essential ? EmailImportance.Essential : EmailImportance.NonEssential,
            EmailClassification.Of(category));
    }

    [Fact]
    public void EveryCategoryIsClassified()
    {
        foreach (var category in Enum.GetValues<EmailCategory>())
            _ = EmailClassification.Of(category); // throws if a category is left unclassified
    }

    [Fact]
    public async Task OptedOutRecipientIsSkippedForNonEssentialEmail()
    {
        var world = new EmailWorld();
        world.Profiles.Items["recipient"] = ProfileFor("recipient", nonEssentialEmailsEnabled: false);

        var result = await world.Service.SendAsync(Reminder("recipient"), TestContext.Current.CancellationToken);

        Assert.True(result.Suppressed);
        Assert.False(result.AlreadyHandled);
        Assert.Empty(world.Capture.Messages);
        Assert.Empty(world.Ledger.Reserved); // never even reserved a delivery slot
    }

    [Fact]
    public async Task OptedOutRecipientStillReceivesEssentialEmail()
    {
        var world = new EmailWorld();
        world.Profiles.Items["recipient"] = ProfileFor("recipient", nonEssentialEmailsEnabled: false);

        var invitation = Templates.Invitation(new(
            "invite-1", "person@example.com", "Pat", "Alex", "Family exchange", ActionUrl));
        var result = await world.Service.SendAsync(invitation, TestContext.Current.CancellationToken);

        Assert.False(result.Suppressed);
        Assert.Single(world.Capture.Messages);
    }

    [Fact]
    public async Task RecipientWithPreferenceEnabledReceivesNonEssentialEmail()
    {
        var world = new EmailWorld();
        world.Profiles.Items["recipient"] = ProfileFor("recipient", nonEssentialEmailsEnabled: true);

        var result = await world.Service.SendAsync(Reminder("recipient"), TestContext.Current.CancellationToken);

        Assert.False(result.Suppressed);
        Assert.Single(world.Capture.Messages);
    }

    [Fact]
    public async Task NonEssentialEmailWithoutAResolvableAccountFailsOpen()
    {
        var world = new EmailWorld(); // no profile stored, and no recipient user id on the message

        var reminderWithoutAccount = Templates.Reminder(new(
            "reminder-1", "person@example.com", "Pat", "Family exchange", "Finish your wishlist.", ActionUrl));
        var result = await world.Service.SendAsync(reminderWithoutAccount, TestContext.Current.CancellationToken);

        Assert.False(result.Suppressed);
        Assert.Single(world.Capture.Messages);
    }

    [Fact]
    public async Task EmailPreferenceTogglesRoundTripThroughTheProfileApi()
    {
        var world = new ProfileWorld();

        // Establish a profile; optional email defaults off until the user explicitly opts in.
        var created = await world.Service.SaveAsync(
            new SaveProfileRequest("Alex", Consent: new ConsentInput("2026.1", "2026-07-19T10:00:00Z")),
            TestContext.Current.CancellationToken);
        Assert.False(created.NonEssentialEmailsEnabled);

        // Opt out.
        var optedOut = await world.Service.SaveAsync(
            new SaveProfileRequest("Alex", NonEssentialEmailsEnabled: false), TestContext.Current.CancellationToken);
        Assert.False(optedOut.NonEssentialEmailsEnabled);
        Assert.False((await world.Service.GetAsync(TestContext.Current.CancellationToken)).NonEssentialEmailsEnabled);

        // A display-name save without the flag must not silently re-enable it.
        var renamed = await world.Service.SaveAsync(new SaveProfileRequest("Alex Rivera"), TestContext.Current.CancellationToken);
        Assert.False(renamed.NonEssentialEmailsEnabled);

        // Opt back in.
        var optedIn = await world.Service.SaveAsync(
            new SaveProfileRequest("Alex Rivera", NonEssentialEmailsEnabled: true), TestContext.Current.CancellationToken);
        Assert.True(optedIn.NonEssentialEmailsEnabled);
    }

    private static TransactionalEmail Reminder(string recipientUserId) => Templates.Reminder(new(
        "reminder-1", "person@example.com", "Pat", "Family exchange", "Finish your wishlist.", ActionUrl, recipientUserId));

    private static ProfileRecord ProfileFor(string userId, bool nonEssentialEmailsEnabled) =>
        new(userId, "Pat", "now", "now", null, nonEssentialEmailsEnabled);

    private sealed class EmailWorld
    {
        public InMemoryProfiles Profiles { get; } = new();
        public CapturingEmailTransport Capture { get; } = new();
        public RecordingLedger Ledger { get; } = new();
        public TransactionalEmailService Service { get; }

        public EmailWorld()
        {
            var gate = new AccountEmailPreferenceGate(Profiles, NullLogger<AccountEmailPreferenceGate>.Instance);
            Service = new TransactionalEmailService(Capture, Ledger, gate, NullLogger<TransactionalEmailService>.Instance);
        }
    }

    private sealed class ProfileWorld
    {
        public InMemoryProfiles Profiles { get; } = new();
        public ProfileService Service { get; }

        public ProfileWorld()
        {
            var settings = new HumbuggSettings("us-east-1", "us-east-1", "pool", "client",
                "http://localhost:5173", "https://humbugg.com", null, "profiles", "groups", "members", "draws",
                "audit", "analytics", AvatarBaseUrl: "https://humbugg.com");
            Service = new ProfileService(new FakeUser(), Profiles, new InMemoryAvatarStore(), settings);
        }
    }

    private sealed class FakeUser : ICurrentUser { public string UserId => "recipient"; }

    private sealed class RecordingLedger : IEmailDeliveryLedger
    {
        public List<string> Reserved { get; } = [];
        public Task<bool> TryBeginAsync(TransactionalEmail email, CancellationToken cancellationToken)
        {
            if (Reserved.Contains(email.MessageId)) return Task.FromResult(false);
            Reserved.Add(email.MessageId);
            return Task.FromResult(true);
        }
        public Task MarkAcceptedAsync(string messageId, CancellationToken cancellationToken) => Task.CompletedTask;
        public Task MarkFailedAsync(string messageId, CancellationToken cancellationToken)
        {
            Reserved.Remove(messageId);
            return Task.CompletedTask;
        }
    }

    private sealed class InMemoryProfiles : IProfileRepository
    {
        public Dictionary<string, ProfileRecord> Items { get; } = new(StringComparer.Ordinal);
        public Task<ProfileRecord?> GetAsync(string userId, CancellationToken cancellationToken = default) =>
            Task.FromResult(Items.TryGetValue(userId, out var record) ? record : null);
        public Task<ProfileRecord> UpsertAsync(string userId, string displayName, bool? nonEssentialEmailsEnabled = null, Consent? consent = null, CancellationToken cancellationToken = default)
        {
            var existing = Items.TryGetValue(userId, out var current) ? current : null;
            var record = new ProfileRecord(
                userId, displayName, existing?.CreatedAt ?? "now", "now", existing?.AvatarKey,
                nonEssentialEmailsEnabled ?? existing?.NonEssentialEmailsEnabled ?? false,
                existing?.ConsentVersion ?? consent?.Version,
                existing?.ConsentAcceptedAt ?? consent?.AcceptedAt);
            Items[userId] = record;
            return Task.FromResult(record);
        }
        public Task<ProfileRecord> SetAvatarKeyAsync(string userId, string? avatarKey, CancellationToken cancellationToken = default)
        {
            if (!Items.TryGetValue(userId, out var record))
                throw ApiException.NotFound("Complete your profile before adding a photo.");
            Items[userId] = record with { AvatarKey = avatarKey };
            return Task.FromResult(Items[userId]);
        }
        public Task DeleteAsync(string userId, CancellationToken cancellationToken = default) { Items.Remove(userId); return Task.CompletedTask; }
    }
}
