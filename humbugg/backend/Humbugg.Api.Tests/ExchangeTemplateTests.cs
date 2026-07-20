using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class ExchangeTemplateTests
{
    [Fact]
    public void DeadlineIsRelativeToTheNewEvent()
    {
        Assert.Equal(new DateOnly(2027, 11, 20), TemplateDates.Deadline(new DateOnly(2027, 12, 20), 30));
        Assert.Equal(new DateOnly(2028, 1, 5), TemplateDates.Deadline(new DateOnly(2028, 1, 5), 0));
    }

    [Fact]
    public void RepositoryKeysAlwaysIncludeTheAuthenticatedOwner()
    {
        var alice = TemplateRepository.Key("alice", "same-template");
        var bob = TemplateRepository.Key("bob", "same-template");
        Assert.Equal("alice", alice["user_id"].S);
        Assert.Equal("bob", bob["user_id"].S);
        Assert.NotEqual(alice["user_id"].S, bob["user_id"].S);
    }

    [Fact]
    public void SnapshotRetainsReuseDataAfterSourceIsGone()
    {
        var snapshot = new ExchangeTemplate(
            "template", "Annual", "Family exchange", "Description", 14, "Add sizes", "none",
            new(ReminderState.Active, true, true, 3, 9, 20), new("Welcome", "Instructions"),
            [new("former-member", "Pat", "pat@example.com")], "deleted-group", "now", "now");
        var detached = snapshot with { SourceGroupId = null };
        Assert.Equal("pat@example.com", detached.PriorParticipants.Single().Email);
        Assert.Equal(14, detached.SignupDeadlineDaysBeforeEvent);
        Assert.Equal("Welcome", detached.Customization.Greeting);
    }
}
