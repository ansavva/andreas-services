using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Data;
using Humbugg.Api.Models;

using Xunit;

namespace Humbugg.Api.IntegrationTests.Data;

public sealed class ProfileRepositoryTests(DevStackFixture stack) : DevStackTest(stack)
{
    private ProfileRepository Repository => new(Db, Settings);

    [IntegrationFact]
    public async Task Upsert_creates_and_round_trips_including_consent()
    {
        var userId = Uid("user");
        CleanupItem(Settings.ProfilesTable, "user_id", userId);

        var created = await Repository.UpsertAsync(userId, "Test Person", nonEssentialEmailsEnabled: true,
            consent: new Consent("2026-01", "2026-08-27T00:00:00Z"));

        Assert.Equal(userId, created.UserId);
        Assert.Equal("Test Person", created.DisplayName);
        Assert.True(created.NonEssentialEmailsEnabled);
        Assert.Equal("2026-01", created.ConsentVersion);

        var fetched = await Repository.GetAsync(userId);
        Assert.NotNull(fetched);
        Assert.Equal(created, fetched);
    }

    [IntegrationFact]
    public async Task Consent_is_written_once_and_email_preference_survives_a_name_save()
    {
        var userId = Uid("user");
        CleanupItem(Settings.ProfilesTable, "user_id", userId);

        await Repository.UpsertAsync(userId, "First Name", nonEssentialEmailsEnabled: true,
            consent: new Consent("2026-01", "2026-08-27T00:00:00Z"));
        var updated = await Repository.UpsertAsync(userId, "Second Name",
            consent: new Consent("2026-09", "2026-09-01T00:00:00Z"));

        Assert.Equal("Second Name", updated.DisplayName);
        // if_not_exists: the original consent record is immutable.
        Assert.Equal("2026-01", updated.ConsentVersion);
        Assert.Equal("2026-08-27T00:00:00Z", updated.ConsentAcceptedAt);
        // A save that carries no preference must not reset the stored opt-in.
        Assert.True(updated.NonEssentialEmailsEnabled);
    }

    [IntegrationFact]
    public async Task A_row_without_the_email_flag_reads_as_opted_out()
    {
        // Rows written before the preference existed have no attribute at all; BoolOrDefault
        // must treat absence as false, not as the record type's default of true.
        var userId = Uid("user");
        CleanupItem(Settings.ProfilesTable, "user_id", userId);
        await Db.PutItemAsync(new PutItemRequest
        {
            TableName = Settings.ProfilesTable,
            Item = new()
            {
                ["user_id"] = new(userId),
                ["display_name"] = new("Legacy Row"),
                ["created_at"] = new(Now()),
                ["updated_at"] = new(Now())
            }
        });

        var fetched = await Repository.GetAsync(userId);
        Assert.NotNull(fetched);
        Assert.False(fetched.NonEssentialEmailsEnabled);
    }

    [IntegrationFact]
    public async Task Avatar_key_sets_clears_and_requires_an_existing_profile()
    {
        var userId = Uid("user");
        CleanupItem(Settings.ProfilesTable, "user_id", userId);

        var missing = await Assert.ThrowsAsync<ApiException>(() => Repository.SetAvatarKeyAsync(userId, "avatars/x.jpg"));
        Assert.Equal(404, missing.StatusCode);

        await Repository.UpsertAsync(userId, "Has Avatar");
        var withAvatar = await Repository.SetAvatarKeyAsync(userId, "avatars/x.jpg");
        Assert.Equal("avatars/x.jpg", withAvatar.AvatarKey);

        var cleared = await Repository.SetAvatarKeyAsync(userId, null);
        Assert.Null(cleared.AvatarKey);
    }

    [IntegrationFact]
    public async Task Delete_is_idempotent()
    {
        var userId = Uid("user");
        await Repository.UpsertAsync(userId, "Doomed");
        await Repository.DeleteAsync(userId);
        await Repository.DeleteAsync(userId); // second delete of an absent row must not throw
        Assert.Null(await Repository.GetAsync(userId));
    }
}
