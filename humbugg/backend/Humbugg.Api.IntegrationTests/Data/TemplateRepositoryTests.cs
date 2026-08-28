using Humbugg.Api.Data;
using Humbugg.Api.Models;

using Xunit;

namespace Humbugg.Api.IntegrationTests.Data;

public sealed class TemplateRepositoryTests(DevStackFixture stack) : DevStackTest(stack)
{
    private TemplateRepository Repository => new(Db, Settings);

    [IntegrationFact]
    public async Task Put_get_list_and_delete_round_trip_the_serialized_shapes()
    {
        var userId = Uid("user");
        var template = new ExchangeTemplate(
            Uid("template"), "Office 2026", "Office Secret Santa", "Annual exchange",
            SignupDeadlineDaysBeforeEvent: 7, WishlistPrompt: "Three ideas, please",
            ExclusionsPolicy: "couples",
            ReminderPreferences: new ReminderSettings(ReminderState.Active, true, false, 5, 8, 21),
            Customization: new ExchangeCustomization("Hello", "Read this", "#101010", "#202020"),
            PriorParticipants: [new TemplateParticipant("member-1", "Alice", "alice@example.test")],
            SourceGroupId: "itest-source-group", CreatedAt: Now(), UpdatedAt: Now());
        CleanupItem(Settings.TemplatesTable, "user_id", userId, "template_id", template.TemplateId);

        await Repository.PutAsync(userId, template, TestContext.Current.CancellationToken);

        // The nested records travel through JSON columns. The participants list is compared
        // structurally (record equality is reference equality for collection members), then the
        // rest of the record whole.
        var fetched = await Repository.GetAsync(userId, template.TemplateId, TestContext.Current.CancellationToken);
        Assert.NotNull(fetched);
        Assert.Equal(template.PriorParticipants, fetched.PriorParticipants);
        Assert.Equal(template with { PriorParticipants = fetched.PriorParticipants }, fetched);

        var listed = await Repository.ListAsync(userId, TestContext.Current.CancellationToken);
        var single = Assert.Single(listed);
        Assert.Equal(template.TemplateId, single.TemplateId);

        await Repository.DeleteAsync(userId, template.TemplateId, TestContext.Current.CancellationToken);
        Assert.Null(await Repository.GetAsync(userId, template.TemplateId, TestContext.Current.CancellationToken));
    }

    [IntegrationFact]
    public async Task A_missing_source_group_reads_back_as_null()
    {
        var userId = Uid("user");
        var template = new ExchangeTemplate(
            Uid("template"), "Bare", "Bare Exchange", "",
            SignupDeadlineDaysBeforeEvent: 0, WishlistPrompt: "", ExclusionsPolicy: "none",
            ReminderPreferences: new ReminderSettings(ReminderState.Stopped, true, true, 3, 9, 20),
            Customization: new ExchangeCustomization(),
            PriorParticipants: [], SourceGroupId: null, CreatedAt: Now(), UpdatedAt: Now());
        CleanupItem(Settings.TemplatesTable, "user_id", userId, "template_id", template.TemplateId);

        await Repository.PutAsync(userId, template, TestContext.Current.CancellationToken);
        var fetched = await Repository.GetAsync(userId, template.TemplateId, TestContext.Current.CancellationToken);

        // Stored as "", must come back as null — the empty string is the wire form, not the model.
        Assert.NotNull(fetched);
        Assert.Null(fetched.SourceGroupId);
    }
}
