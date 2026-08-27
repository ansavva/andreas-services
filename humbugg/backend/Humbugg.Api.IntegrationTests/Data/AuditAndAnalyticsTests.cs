using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Data;
using Humbugg.Api.Models;

using Xunit;

namespace Humbugg.Api.IntegrationTests.Data;

public sealed class AuditRepositoryTests(DevStackFixture stack) : DevStackTest(stack)
{
    private AuditRepository Repository => new(Db, Settings);

    private AuditEvent NewEvent(string groupId, string actorUserId) => new(
        groupId, Uid("event"), AuditAction.GroupCreated, actorUserId,
        TargetType: "group", TargetId: groupId, OrganizationId: null,
        CorrelationId: Uid("correlation"), CreatedAt: Now(),
        Metadata: new Dictionary<string, string> { ["source"] = "integration-test" });

    [IntegrationFact]
    public async Task Append_is_append_only()
    {
        var auditEvent = NewEvent(Uid("group"), Uid("actor"));
        CleanupItem(Settings.AuditEventsTable, "group_id", auditEvent.GroupId, "event_id", auditEvent.EventId);

        await Repository.AppendAsync(auditEvent);
        await Assert.ThrowsAsync<ConditionalCheckFailedException>(() => Repository.AppendAsync(auditEvent));
    }

    [IntegrationFact]
    public async Task Anonymizer_rewrites_only_the_actor_and_is_idempotent()
    {
        var actor = Uid("actor");
        var bystanderActor = Uid("actor");
        var mine = NewEvent(Uid("group"), actor);
        var alsoMine = NewEvent(Uid("group"), actor);
        var theirs = NewEvent(Uid("group"), bystanderActor);
        foreach (var auditEvent in new[] { mine, alsoMine, theirs })
        {
            CleanupItem(Settings.AuditEventsTable, "group_id", auditEvent.GroupId, "event_id", auditEvent.EventId);
            await Repository.AppendAsync(auditEvent);
        }

        var anonymizer = new AuditActorAnonymizer(Db, Settings);
        Assert.Equal(2, await anonymizer.AnonymizeActorAsync(actor, "anon-xyz"));
        // The scan no longer finds the real subject, so a retried deletion rewrites nothing.
        Assert.Equal(0, await anonymizer.AnonymizeActorAsync(actor, "anon-xyz"));

        var rewritten = await Db.GetItemAsync(Settings.AuditEventsTable, new Dictionary<string, AttributeValue>
        {
            ["group_id"] = new(mine.GroupId),
            ["event_id"] = new(mine.EventId)
        });
        Assert.Equal("anon-xyz", rewritten.Item["actor_user_id"].S);
        // Everything but the actor survives, and other actors' records are untouched.
        Assert.Equal("group_created", rewritten.Item["action"].S);
        var untouched = await Db.GetItemAsync(Settings.AuditEventsTable, new Dictionary<string, AttributeValue>
        {
            ["group_id"] = new(theirs.GroupId),
            ["event_id"] = new(theirs.EventId)
        });
        Assert.Equal(bystanderActor, untouched.Item["actor_user_id"].S);
    }
}

public sealed class AnalyticsSinkTests(DevStackFixture stack) : DevStackTest(stack)
{
    [IntegrationFact]
    public async Task A_repeated_idempotency_key_is_a_silent_no_op()
    {
        var sink = new DynamoDbAnalyticsSink(Db, Settings);
        var key = Uid("idem");
        CleanupItem(Settings.AnalyticsEventsTable, "idempotency_key", key);

        await sink.RecordAsync(new AnalyticsEvent(AnalyticsEventType.DrawCompleted, PlanCode.Free,
            "itest-group", key, Now(), new Dictionary<string, string> { ["participants"] = "4" }));
        // Same key, different payload: must neither throw nor overwrite the first row.
        await sink.RecordAsync(new AnalyticsEvent(AnalyticsEventType.GroupCreated, PlanCode.Plus,
            "itest-other-group", key, Now(), new Dictionary<string, string>()));

        var stored = await Db.GetItemAsync(Settings.AnalyticsEventsTable,
            new Dictionary<string, AttributeValue> { ["idempotency_key"] = new(key) });
        Assert.Equal("draw_completed", stored.Item["event_type"].S);
        Assert.Equal("free", stored.Item["plan"].S);
        Assert.Equal("4", stored.Item["dimensions"].M["participants"].S);
    }
}
