using Humbugg.Api.Data;
using Humbugg.Api.Models;

using Xunit;

namespace Humbugg.Api.IntegrationTests.Data;

public sealed class ReminderRepositoryTests(DevStackFixture stack) : DevStackTest(stack)
{
    private ReminderRepository Repository => new(Db, Settings);

    private ReminderConfigurationRecord NewConfiguration(string groupId, string? next) => new(
        groupId, ReminderState.Active, RemindUnacceptedInvitations: true, RemindIncompleteReadiness: false,
        IntervalDays: 3, QuietStartUtcHour: 9, QuietEndUtcHour: 20,
        NextScheduledAt: next, LastManualAt: null, UpdatedAt: Now());

    private string TrackGroup()
    {
        var groupId = Uid("group");
        CleanupItem(Settings.RemindersTable, "group_id", groupId, "record_key", "CONFIG");
        return groupId;
    }

    [IntegrationFact]
    public async Task Configuration_round_trips_including_null_schedule()
    {
        var groupId = TrackGroup();
        var configuration = NewConfiguration(groupId, next: null);

        await Repository.SaveConfigurationAsync(configuration);
        var fetched = await Repository.GetConfigurationAsync(groupId);

        Assert.Equal(configuration, fetched); // NULL attributes must read back as null strings
        Assert.Null(await Repository.GetConfigurationAsync(Uid("group")));
    }

    [IntegrationFact]
    public async Task GetDue_finds_active_due_configurations_and_skips_stopped_ones()
    {
        var dueGroup = TrackGroup();
        var stoppedGroup = TrackGroup();
        var past = DateTimeOffset.UtcNow.AddMinutes(-5).ToString("O");
        await Repository.SaveConfigurationAsync(NewConfiguration(dueGroup, past));
        await Repository.SaveConfigurationAsync(NewConfiguration(stoppedGroup, past) with { State = ReminderState.Stopped });

        var due = await Repository.GetDueAsync(Now());

        // The reminders table is shared with other residents of the dev stack, so assert
        // containment rather than an exact set.
        Assert.Contains(due, configuration => configuration.GroupId == dueGroup);
        Assert.DoesNotContain(due, configuration => configuration.GroupId == stoppedGroup);
    }

    [IntegrationFact]
    public async Task Automatic_run_claims_are_compare_and_swap()
    {
        var groupId = TrackGroup();
        var expected = DateTimeOffset.UtcNow.AddMinutes(-5).ToString("O");
        var next = DateTimeOffset.UtcNow.AddDays(3).ToString("O");
        await Repository.SaveConfigurationAsync(NewConfiguration(groupId, expected));

        Assert.True(await Repository.ClaimAutomaticRunAsync(groupId, expected, next));
        // A concurrent worker holding the same stale expectation must lose, not double-send.
        Assert.False(await Repository.ClaimAutomaticRunAsync(groupId, expected, next));
        Assert.Equal(next, (await Repository.GetConfigurationAsync(groupId))!.NextScheduledAt);
    }

    [IntegrationFact]
    public async Task Manual_run_claims_respect_the_cutoff()
    {
        var groupId = TrackGroup();
        await Repository.SaveConfigurationAsync(NewConfiguration(groupId, next: null));
        var now = Now();
        var cutoff = DateTimeOffset.UtcNow.AddHours(-1).ToString("O");

        Assert.True(await Repository.ClaimManualRunAsync(groupId, cutoff, now));
        // The claim just recorded last_manual_at = now, which is after the cutoff.
        Assert.False(await Repository.ClaimManualRunAsync(groupId, cutoff, Now()));
        // And a claim against a group with no configuration at all must fail, not upsert.
        Assert.False(await Repository.ClaimManualRunAsync(Uid("group"), cutoff, Now()));
    }

    [IntegrationFact]
    public async Task History_reads_newest_first_and_respects_the_limit()
    {
        var groupId = Uid("group");
        var older = new ReminderHistoryItem(Uid("reminder"), ReminderRule.UnacceptedInvitation,
            "invitation-1", "sent", "2026-08-01T00:00:00.0000000Z");
        var newer = new ReminderHistoryItem(Uid("reminder"), ReminderRule.IncompleteReadiness,
            "invitation-2", "sent", "2026-08-02T00:00:00.0000000Z");
        await Repository.SaveHistoryAsync(groupId, older);
        await Repository.SaveHistoryAsync(groupId, newer);
        CleanupItem(Settings.RemindersTable, "group_id", groupId, "record_key", $"H#{older.CreatedAt}#{older.ReminderId}");
        CleanupItem(Settings.RemindersTable, "group_id", groupId, "record_key", $"H#{newer.CreatedAt}#{newer.ReminderId}");

        var history = await Repository.GetHistoryAsync(groupId, limit: 10);
        Assert.Equal([newer, older], history);

        var limited = await Repository.GetHistoryAsync(groupId, limit: 1);
        Assert.Equal([newer], limited);
    }
}
