using System.Globalization;
using Humbugg.Api;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Xunit;

namespace Humbugg.Api.Tests;

// GDPR Art. 7 — signup must actively record demonstrable consent (policy version + UTC timestamp).
public sealed class ConsentTests
{
    [Fact]
    public async Task CreatingAProfileWithoutConsentIsRejected()
    {
        var world = new ProfileWorld();

        var error = await Assert.ThrowsAsync<ApiException>(() =>
            world.Service.SaveAsync(new SaveProfileRequest("Alex"), TestContext.Current.CancellationToken));

        Assert.Equal(400, error.StatusCode);
        // Nothing is persisted when consent is missing, so no account is created.
        Assert.Null(await world.Profiles.GetAsync("user", TestContext.Current.CancellationToken));
    }

    [Fact]
    public async Task CreatingAProfileWithConsentPersistsVersionAndUtcTimestamp()
    {
        var world = new ProfileWorld();

        var profile = await world.Service.SaveAsync(
            new SaveProfileRequest("Alex", Consent: new ConsentInput("2026.1", "2026-07-19T10:30:00Z")),
            TestContext.Current.CancellationToken);

        Assert.NotNull(profile.Consent);
        Assert.Equal("2026.1", profile.Consent!.Version);
        var acceptedAt = DateTimeOffset.Parse(profile.Consent.AcceptedAt, CultureInfo.InvariantCulture);
        Assert.Equal(TimeSpan.Zero, acceptedAt.Offset); // stored as UTC
        Assert.Equal(DateTimeOffset.Parse("2026-07-19T10:30:00Z", CultureInfo.InvariantCulture), acceptedAt);

        // GET returns the recorded consent so it can be surfaced later (e.g. in the GDPR data export).
        var fetched = await world.Service.GetAsync(TestContext.Current.CancellationToken);
        Assert.Equal("2026.1", fetched.Consent!.Version);
    }

    [Fact]
    public async Task ConsentIsImmutableAndLaterSavesDoNotRequireIt()
    {
        var world = new ProfileWorld();
        await world.Service.SaveAsync(
            new SaveProfileRequest("Alex", Consent: new ConsentInput("2026.1", "2026-07-19T10:30:00Z")),
            TestContext.Current.CancellationToken);

        // A later rename with no consent succeeds and never overwrites the original signup record,
        // even if a different version is supplied.
        var renamed = await world.Service.SaveAsync(
            new SaveProfileRequest("Alex Rivera", Consent: new ConsentInput("9999.9", "2030-01-01T00:00:00Z")),
            TestContext.Current.CancellationToken);

        Assert.Equal("2026.1", renamed.Consent!.Version);
        Assert.Equal(
            DateTimeOffset.Parse("2026-07-19T10:30:00Z", CultureInfo.InvariantCulture),
            DateTimeOffset.Parse(renamed.Consent.AcceptedAt, CultureInfo.InvariantCulture));
    }

    [Theory]
    [InlineData("", "2026-07-19T10:30:00Z")]
    [InlineData("2026.1", "")]
    [InlineData("2026.1", "not-a-timestamp")]
    public async Task InvalidConsentPayloadsAreRejected(string version, string acceptedAt)
    {
        var world = new ProfileWorld();

        var error = await Assert.ThrowsAsync<ApiException>(() =>
            world.Service.SaveAsync(
                new SaveProfileRequest("Alex", Consent: new ConsentInput(version, acceptedAt)),
                TestContext.Current.CancellationToken));

        Assert.Equal(400, error.StatusCode);
    }

    private sealed class ProfileWorld
    {
        public InMemoryProfiles Profiles { get; } = new();
        public ProfileService Service { get; }

        public ProfileWorld()
        {
            var settings = new HumbuggSettings("us-east-1", "us-east-1", "pool", "client",
                ["http://localhost:5173"], "https://humbugg.com", null, "profiles", "groups", "members", "draws",
                "audit", "analytics", AvatarBaseUrl: "https://humbugg.com");
            Service = new ProfileService(new FakeUser(), Profiles, new InMemoryAvatarStore(), settings);
        }
    }

    private sealed class FakeUser : ICurrentUser { public string UserId => "user"; }

    private sealed class InMemoryProfiles : IProfileRepository
    {
        public Dictionary<string, ProfileRecord> Items { get; } = new(StringComparer.Ordinal);
        public Task<ProfileRecord?> GetAsync(string userId, CancellationToken cancellationToken = default) =>
            Task.FromResult(Items.TryGetValue(userId, out var record) ? record : null);
        public Task<ProfileRecord> UpsertAsync(string userId, string displayName, bool? nonEssentialEmailsEnabled = null, Consent? consent = null, CancellationToken cancellationToken = default)
        {
            var existing = Items.TryGetValue(userId, out var current) ? current : null;
            // Mirror the repository's if_not_exists semantics: consent is written once and never overwritten.
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
