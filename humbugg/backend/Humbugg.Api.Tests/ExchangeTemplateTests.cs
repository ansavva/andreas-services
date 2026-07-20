using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Xunit;
using System.Reflection;
using Amazon.DynamoDBv2.Model;

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

    [Fact]
    public async Task OtherUserCannotReadUpdateApplyOrDeleteOwnersTemplate()
    {
        var store = new FakeTemplates("owner", Template());
        var subject = new ExchangeTemplateService(new User("other"), store, null!, null!, null!, null!, null!, null!, null!);
        Assert.Empty(await subject.ListAsync(TestContext.Current.CancellationToken));
        await Assert.ThrowsAsync<ApiException>(() => subject.UpdateAsync("template", new(null, null, null, null, null, null, null, null), TestContext.Current.CancellationToken));
        await Assert.ThrowsAsync<ApiException>(() => subject.ApplyAsync("template", new("target", "2028-12-20", []), TestContext.Current.CancellationToken));
        await Assert.ThrowsAsync<ApiException>(() => subject.DeleteAsync("template", TestContext.Current.CancellationToken));
        Assert.False(store.Deleted);
    }

    [Fact]
    public async Task AppliesDetachedSnapshotAndInvitesExactlyConfirmedCandidates()
    {
        var store = new FakeTemplates("owner", Template() with { SourceGroupId = "already-deleted" });
        var groups = new FakeGroups(new GroupRecord("target", "owner", "Target", "", null, null, null, "USD", PlanCode.Plus, "plus:target", GroupStatus.Open, "hash", [], "now", "now"));
        var memberProxy = Proxy<IMembershipRepository>();
        memberProxy.Handlers[nameof(IMembershipRepository.GetByGroupAsync)] = _ => Task.FromResult<IReadOnlyList<MembershipRecord>>([
            new("organizer", "target", "owner", "Owner", true, true, "", "", new(), "now", "now")
        ]);
        var rowProxy = Proxy<IInvitationRepository>();
        rowProxy.Handlers[nameof(IInvitationRepository.GetByGroupAsync)] = _ => Task.FromResult<IReadOnlyList<InvitationRecord>>([]);
        var sent = new List<string>();
        var invitationProxy = Proxy<IInvitationService>();
        invitationProxy.Handlers[nameof(IInvitationService.CreateAsync)] = args => { sent.AddRange(((CreateInvitationsRequest)args[1]!).Emails!); return Task.FromResult(new CreateInvitationsResponse([])); };
        var reminderProxy = Proxy<IReminderService>();
        reminderProxy.Handlers[nameof(IReminderService.UpdateAsync)] = _ => Task.FromResult(new ReminderOverview(new(ReminderState.Active, true, true, 3, 9, 20), null, []));
        var groupProxy = Proxy<IGroupService>();
        groupProxy.Handlers[nameof(IGroupService.UpdateAsync)] = _ => Task.FromResult(Detail());
        groupProxy.Handlers[nameof(IGroupService.UpdateCustomizationAsync)] = _ => Task.FromResult(Detail());
        groupProxy.Handlers[nameof(IGroupService.SetExclusionsAsync)] = _ => Task.FromResult(Detail());
        groupProxy.Handlers[nameof(IGroupService.GetAsync)] = _ => Task.FromResult(Detail());
        var subject = new ExchangeTemplateService(new User("owner"), store, groups, memberProxy.Instance, rowProxy.Instance, invitationProxy.Instance, reminderProxy.Instance, new PlanCatalog(new()), groupProxy.Instance);

        await subject.ApplyAsync("template", new("target", "2028-12-20", ["pat"]), TestContext.Current.CancellationToken);

        Assert.Equal(["pat@example.com"], sent);
        Assert.Single(await memberProxy.Instance.GetByGroupAsync("target", TestContext.Current.CancellationToken), x => x.IsOrganizer);
    }

    private static ExchangeTemplate Template() => new("template", "Annual", "Family", "Description", 14, "Sizes", "none",
        new(ReminderState.Active, true, true, 3, 9, 20), new("Welcome", "Instructions"),
        [new("pat", "Pat", "pat@example.com"), new("sam", "Sam", "sam@example.com")], "source", "now", "now");
    private static GroupDetail Detail() => new("target", "Family", GroupStatus.Open, "2028-12-20", null, "USD", PlanCode.Plus, 50, true, "now", "now", "", "2028-12-06", [], []);
    private sealed record User(string UserId) : ICurrentUser { public string? Email => "owner@example.com"; }
    private sealed class FakeTemplates(string owner, ExchangeTemplate template) : ITemplateRepository
    {
        public bool Deleted { get; private set; }
        public Task<IReadOnlyList<ExchangeTemplate>> ListAsync(string userId, CancellationToken ct) => Task.FromResult<IReadOnlyList<ExchangeTemplate>>(userId == owner ? [template] : []);
        public Task<ExchangeTemplate?> GetAsync(string userId, string id, CancellationToken ct) => Task.FromResult<ExchangeTemplate?>(userId == owner && id == template.TemplateId ? template : null);
        public Task PutAsync(string userId, ExchangeTemplate value, CancellationToken ct) => Task.CompletedTask;
        public Task DeleteAsync(string userId, string id, CancellationToken ct) { Deleted = true; return Task.CompletedTask; }
    }
    private sealed class FakeGroups(GroupRecord target) : IGroupRepository
    {
        public Task<GroupRecord?> GetAsync(string id, CancellationToken ct = default) => Task.FromResult<GroupRecord?>(id == target.GroupId ? target : null);
        public Task<GroupRecord> CreateAsync(GroupRecord value, CancellationToken ct = default) => throw new NotImplementedException();
        public Task<GroupRecord> UpdateAsync(string id, IReadOnlyDictionary<string, AttributeValue> fields, GroupStatus? expectedStatus = null, CancellationToken ct = default) => throw new NotImplementedException();
        public Task DeleteAsync(string id, CancellationToken ct = default) => throw new NotImplementedException();
        public Task CreateDrawAsync(string id, IReadOnlyDictionary<string, string> assignments, string actor, CancellationToken ct = default) => throw new NotImplementedException();
        public Task<DrawRecord?> GetDrawAsync(string id, CancellationToken ct = default) => throw new NotImplementedException();
        public Task ResetDrawAsync(string id, CancellationToken ct = default) => throw new NotImplementedException();
    }
    private static ProxyHandle<T> Proxy<T>() where T : class
    {
        var instance = DispatchProxy.Create<T, TestProxy>();
        return new(instance, (TestProxy)(object)instance);
    }
    private sealed record ProxyHandle<T>(T Instance, TestProxy Proxy) where T : class { public Dictionary<string, Func<object?[], object?>> Handlers => Proxy.Handlers; }
    public class TestProxy : DispatchProxy
    {
        public Dictionary<string, Func<object?[], object?>> Handlers { get; } = new();
        protected override object? Invoke(MethodInfo? method, object?[]? args) => Handlers.TryGetValue(method!.Name, out var handler) ? handler(args ?? []) : throw new NotImplementedException(method.Name);
    }
}
