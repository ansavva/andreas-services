using Amazon.DynamoDBv2.Model;
using Humbugg.Api;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Humbugg.Api.Services.Email.Core;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class ReminderAuthorizationTests
{
    [Fact]
    public async Task CoOrganizerCanReadAndConfigureReminders()
    {
        var repository = new FakeReminders();
        var subject = CreateSubject(organizer: true, repository);

        await subject.GetAsync("group", TestContext.Current.CancellationToken);
        var result = await subject.UpdateAsync(
            "group",
            new(
                ReminderState.Active,
                RemindUnacceptedInvitations: true,
                RemindIncompleteReadiness: true),
            TestContext.Current.CancellationToken);

        Assert.Equal(ReminderState.Active, result.Settings.State);
        Assert.NotNull(repository.Configuration);
    }

    [Fact]
    public async Task OrdinaryParticipantCannotReadOrConfigureReminders()
    {
        var repository = new FakeReminders();
        var subject = CreateSubject(organizer: false, repository);

        var read = await Assert.ThrowsAsync<ApiException>(() =>
            subject.GetAsync("group", TestContext.Current.CancellationToken));
        var update = await Assert.ThrowsAsync<ApiException>(() =>
            subject.UpdateAsync(
                "group",
                new(ReminderState.Active, true, true),
                TestContext.Current.CancellationToken));

        Assert.Equal(403, read.StatusCode);
        Assert.Equal(403, update.StatusCode);
        Assert.Null(repository.Configuration);
    }

    private static ReminderService CreateSubject(bool organizer, FakeReminders reminders) =>
        new(
            new FakeUser(),
            new FakeGroups(),
            new FakeMembers(organizer),
            new FakeInvitations(),
            reminders,
            new PlanCatalog(new()),
            new TransactionalEmailTemplates(),
            new FakeEmail(),
            new FakeAudit(),
            new HumbuggSettings(
                "us-east-1", "us-east-1", "pool", "client",
                ["http://localhost:5173"], "http://localhost:5173", null,
                "profiles", "groups", "members", "draws", "audit", "analytics"));

    private sealed class FakeUser : ICurrentUser
    {
        public string UserId => "user";
    }

    private sealed class FakeGroups : IGroupRepository
    {
        private static readonly GroupRecord Group = new(
            "group", "owner", "Exchange", "", null, null, null, "USD",
            PlanCode.Plus, "plus:paid", GroupStatus.Open, "hash", [], "now", "now");
        public Task<GroupRecord?> GetAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<GroupRecord?>(Group);
        public Task<GroupRecord> CreateAsync(GroupRecord group, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<GroupRecord> UpdateAsync(string groupId, IReadOnlyDictionary<string, AttributeValue> fields, GroupStatus? expectedStatus = null, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task CreateDrawAsync(string groupId, IReadOnlyDictionary<string, string> assignments, string actorUserId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<DrawRecord?> GetDrawAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task ResetDrawAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class FakeMembers(bool organizer) : IMembershipRepository
    {
        public Task<MembershipRecord?> GetByUserAndGroupAsync(string userId, string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<MembershipRecord?>(MembershipRepository.NewRecord(groupId, userId, "User", organizer));
        public Task<MembershipRecord?> GetAsync(string memberId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        // Not exercised here: this fake's service never reads an assignment.
        public Task SetWishClaimAsync(string memberId, string drawId, string wishId, WishClaimRecord claim, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
        public Task RemoveWishClaimAsync(string memberId, string drawId, string wishId, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
        public Task ClearWishClaimsAsync(string memberId, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
        public Task MarkAssignmentViewedAsync(string memberId, string drawId, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
        public Task<IReadOnlyList<MembershipRecord>> GetByUserAsync(string userId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<IReadOnlyList<MembershipRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> CreateAsync(string groupId, string userId, string displayName, bool organizer, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdatePrivateAsync(string memberId, string wishlist, string avoidances, Address address, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdateParticipationAsync(string memberId, bool participating, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task AnonymizeAsync(string memberId, string pseudonym, string displayName, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string memberId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class FakeInvitations : IInvitationRepository
    {
        public Task CreateAsync(InvitationRecord value, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<InvitationRecord?> GetAsync(string invitationId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<IReadOnlyList<InvitationRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task UpdateAsync(string invitationId, string status, string? tokenHash, string? expiresAt, string? messageId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task AcceptAndCreateMembershipAsync(string invitationId, string userId, MembershipRecord membership, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<string?> GetDeliveryStatusAsync(string? messageId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class FakeReminders : IReminderRepository
    {
        public ReminderConfigurationRecord? Configuration { get; private set; }
        public Task<ReminderConfigurationRecord?> GetConfigurationAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult(Configuration);
        public Task SaveConfigurationAsync(ReminderConfigurationRecord configuration, CancellationToken cancellationToken = default)
        {
            Configuration = configuration;
            return Task.CompletedTask;
        }
        public Task<IReadOnlyList<ReminderHistoryItem>> GetHistoryAsync(string groupId, int limit, CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<ReminderHistoryItem>>([]);
        public Task<IReadOnlyList<ReminderConfigurationRecord>> GetDueAsync(string now, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<bool> ClaimAutomaticRunAsync(string groupId, string expectedNext, string next, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<bool> ClaimManualRunAsync(string groupId, string cutoff, string now, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task SaveHistoryAsync(string groupId, ReminderHistoryItem item, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class FakeEmail : ITransactionalEmailService
    {
        public Task<EmailSendResult> SendAsync(TransactionalEmail email, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
    }

    private sealed class FakeAudit : IAuditTrail
    {
        public Task RecordAsync(AuditAction action, string groupId, AuditTarget target, IReadOnlyDictionary<string, string>? metadata = null, string? organizationId = null, CancellationToken cancellationToken = default) =>
            Task.CompletedTask;
    }
}
