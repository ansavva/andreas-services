using Amazon.DynamoDBv2.Model;
using Humbugg.Api;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Humbugg.Api.Services.Email.Core;
using Xunit;

namespace Humbugg.Api.Tests;

// #675: a nudge to somebody who has not accepted their invitation used to link to /groups/{id},
// where a non-member cannot go. It now does what "Send again" does — mints a fresh secret, stores
// its hash, and links to /join/{id}#managed=… — while a reminder to a member still opens the group.
public sealed class ReminderInviteeLinkTests
{
    private const string GroupId = "group";

    [Fact]
    public async Task NudgeToAnInviteeCarriesAFreshInvitationLinkAndStoresItsHash()
    {
        var invitation = Invitation("inv-1", status: "sent", acceptedUserId: null);
        var invitations = new FakeInvitations(invitation);
        var email = new CapturingEmail();
        var subject = CreateSubject(invitations, email);

        await subject.SendManualAsync(
            GroupId,
            new ManualReminderRequest("inv-1", ReminderRule.UnacceptedInvitation),
            TestContext.Current.CancellationToken);

        var sent = Assert.Single(email.Sent);
        var link = sent.TextBody.Split('\n').Single(line => line.StartsWith("View your invitation: ", StringComparison.Ordinal))["View your invitation: ".Length..];
        Assert.StartsWith($"http://localhost:8081/join/{GroupId}#managed=inv-1.", link);
        var secret = link[(link.IndexOf('.', link.IndexOf("#managed=", StringComparison.Ordinal)) + 1)..];

        var stored = Assert.Single(invitations.Items);
        Assert.Equal(InvitationLinks.Hash(secret), stored.TokenHash);
        Assert.NotEqual("old-hash", stored.TokenHash);
        Assert.Equal(sent.MessageId, stored.MessageId);
        Assert.Contains("have not joined yet", sent.TextBody);
        Assert.DoesNotContain("/groups/", sent.TextBody);
    }

    [Fact]
    public async Task NudgeToAMemberOpensTheExchangeAndLeavesTheInvitationAlone()
    {
        var invitation = Invitation("inv-2", status: "accepted", acceptedUserId: "member-user");
        var invitations = new FakeInvitations(invitation);
        var email = new CapturingEmail();
        var subject = CreateSubject(invitations, email);

        await subject.SendManualAsync(
            GroupId,
            new ManualReminderRequest("inv-2", ReminderRule.IncompleteReadiness),
            TestContext.Current.CancellationToken);

        var sent = Assert.Single(email.Sent);
        Assert.Contains($"Open the exchange: http://localhost:8081/groups/{GroupId}", sent.TextBody);
        Assert.Contains("Hello User,", sent.TextBody);
        Assert.Equal("old-hash", Assert.Single(invitations.Items).TokenHash);
    }

    private static InvitationRecord Invitation(string id, string status, string? acceptedUserId) => new(
        id, GroupId, "person@humbugg.test", "old-hash", status,
        ExpiresAt: DateTimeOffset.UtcNow.AddDays(7).ToString("O"), CreatedAt: "now", UpdatedAt: "now",
        AcceptedAt: acceptedUserId is null ? null : "now", AcceptedUserId: acceptedUserId);

    private static ReminderService CreateSubject(FakeInvitations invitations, CapturingEmail email) =>
        new(
            new FakeUser(),
            new FakeGroups(),
            new FakeMembers(),
            invitations,
            new FakeReminders(),
            new PlanCatalog(new()),
            new TransactionalEmailTemplates(),
            email,
            new FakeAudit(),
            new HumbuggSettings(
                "us-east-1", "us-east-1", "pool", "client",
                ["http://localhost:8081"], "http://localhost:8081", null,
                "profiles", "groups", "members", "draws", "audit", "analytics"));

    private sealed class FakeUser : ICurrentUser
    {
        public string UserId => "organizer-user";
    }

    private sealed class FakeGroups : IGroupRepository
    {
        private static readonly GroupRecord Group = new(
            GroupId, "organizer-user", "Office Secret Santa", "", null, null, null, "USD",
            PlanCode.Plus, "plus:paid", GroupStatus.Open, "hash", [], "now", "now");
        public Task<GroupRecord?> GetAsync(string groupId, CancellationToken cancellationToken = default) => Task.FromResult<GroupRecord?>(Group);
        public Task<GroupRecord> CreateAsync(GroupRecord group, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task<GroupRecord> UpdateAsync(string groupId, IReadOnlyDictionary<string, AttributeValue> fields, GroupStatus? expectedStatus = null, string? expectedUpdatedAt = null, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task DeleteAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task CreateDrawAsync(string groupId, IReadOnlyDictionary<string, string> assignments, string actorUserId, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task<DrawRecord?> GetDrawAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task ResetDrawAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotSupportedException();
    }

    // Everyone this fake is asked about is an organizer named "User" with no wishlist — enough for
    // RequireManager to pass and for the readiness rule to find a member who still needs nudging.
    private sealed class FakeMembers : IMembershipRepository
    {
        public Task<MembershipRecord?> GetByUserAndGroupAsync(string userId, string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<MembershipRecord?>(MembershipRepository.NewRecord(groupId, userId, "User", organizer: true));
        public Task<MembershipRecord?> GetAsync(string memberId, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task SetGiftStageAsync(string memberId, string drawId, GiftStage stage, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task SetGiftReceivedAsync(string memberId, string drawId, bool received, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task ClearGiftProgressAsync(string memberId, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task SetWishClaimAsync(string memberId, string drawId, string wishId, WishClaimRecord claim, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task RemoveWishClaimAsync(string memberId, string drawId, string wishId, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task ClearWishClaimsAsync(string memberId, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task MarkAssignmentViewedAsync(string memberId, string drawId, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task<IReadOnlyList<MembershipRecord>> GetByUserAsync(string userId, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task<IReadOnlyList<MembershipRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task<MembershipRecord> CreateAsync(string groupId, string userId, string displayName, bool organizer, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task<MembershipRecord> UpdatePrivateAsync(string memberId, string wishlist, string avoidances, Address address, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task<MembershipRecord> UpdateParticipationAsync(string memberId, bool participating, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task AnonymizeAsync(string memberId, string pseudonym, string displayName, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task DeleteAsync(string memberId, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotSupportedException();
    }

    private sealed class FakeReminders : IReminderRepository
    {
        public Task<ReminderConfigurationRecord?> GetConfigurationAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<ReminderConfigurationRecord?>(new(groupId, ReminderState.Active, true, true, 3, 9, 20, "next", "now", "now"));
        public Task SaveConfigurationAsync(ReminderConfigurationRecord configuration, CancellationToken cancellationToken = default) => Task.CompletedTask;
        public Task<IReadOnlyList<ReminderHistoryItem>> GetHistoryAsync(string groupId, int limit, CancellationToken cancellationToken = default) => Task.FromResult<IReadOnlyList<ReminderHistoryItem>>([]);
        public Task<IReadOnlyList<ReminderConfigurationRecord>> GetDueAsync(string now, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task<bool> ClaimAutomaticRunAsync(string groupId, string expectedNext, string next, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task<bool> ClaimManualRunAsync(string groupId, string cutoff, string now, CancellationToken cancellationToken = default) => Task.FromResult(true);
        public Task SaveHistoryAsync(string groupId, ReminderHistoryItem item, CancellationToken cancellationToken = default) => Task.CompletedTask;
    }

    private sealed class CapturingEmail : ITransactionalEmailService
    {
        public List<TransactionalEmail> Sent { get; } = [];
        public Task<EmailSendResult> SendAsync(TransactionalEmail email, CancellationToken cancellationToken = default)
        {
            Sent.Add(email);
            return Task.FromResult(new EmailSendResult(email.MessageId, email.Category, false, false, null));
        }
    }

    private sealed class FakeAudit : IAuditTrail
    {
        public Task RecordAsync(AuditAction action, string groupId, AuditTarget target, IReadOnlyDictionary<string, string>? metadata = null, string? organizationId = null, CancellationToken cancellationToken = default) =>
            Task.CompletedTask;
    }
}
