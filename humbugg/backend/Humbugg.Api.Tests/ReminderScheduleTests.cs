using Humbugg.Api.Services;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class ReminderScheduleTests
{
    [Theory]
    [InlineData(8, false)]
    [InlineData(9, true)]
    [InlineData(19, true)]
    [InlineData(20, false)]
    public void SendingWindowUsesInclusiveStartAndExclusiveEnd(int hour, bool expected)
    {
        var timestamp = new DateTimeOffset(2026, 7, 20, hour, 0, 0, TimeSpan.Zero);

        Assert.Equal(expected, ReminderSchedule.IsWithinWindow(timestamp, 9, 20));
    }

    [Fact]
    public void BeforeWindowMovesToStartOnSameDay()
    {
        var timestamp = new DateTimeOffset(2026, 7, 20, 6, 30, 0, TimeSpan.Zero);

        var aligned = ReminderSchedule.AlignToWindow(timestamp, 9, 20);

        Assert.Equal(new DateTimeOffset(2026, 7, 20, 9, 0, 0, TimeSpan.Zero), aligned);
    }

    [Fact]
    public void AfterWindowMovesToStartOnNextDay()
    {
        var timestamp = new DateTimeOffset(2026, 7, 20, 22, 30, 0, TimeSpan.Zero);

        var aligned = ReminderSchedule.AlignToWindow(timestamp, 9, 20);

        Assert.Equal(new DateTimeOffset(2026, 7, 21, 9, 0, 0, TimeSpan.Zero), aligned);
    }

    [Fact]
    public void AutomaticProcessingDoesNotCapThePlusInvitationRoster()
    {
        var source = File.ReadAllText(ReminderServicePath());

        Assert.DoesNotContain("groupInvitations.Take(", source, StringComparison.Ordinal);
        Assert.Contains("foreach (var invitation in groupInvitations)", source, StringComparison.Ordinal);
    }

    [Fact]
    public void ManualEligibilityIsCheckedBeforeCooldownIsClaimed()
    {
        var source = File.ReadAllText(ReminderServicePath());
        var method = source[source.IndexOf("public async Task<ReminderHistoryItem> SendManualAsync", StringComparison.Ordinal)..];

        Assert.True(
            method.IndexOf("ResolveReminderAsync(", StringComparison.Ordinal) <
            method.IndexOf("ClaimManualRunAsync(", StringComparison.Ordinal));
    }

    private static string ReminderServicePath()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null)
        {
            var candidate = Path.Combine(directory.FullName, "Humbugg.Api", "Services", "ReminderService.cs");
            if (File.Exists(candidate)) return candidate;
            directory = directory.Parent;
        }
        throw new FileNotFoundException("Could not locate ReminderService.cs.");
    }
}
