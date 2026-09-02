using Amazon.DynamoDBv2.Model;
using Humbugg.Api;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Humbugg.Api.Services.Email.Core;
using System.Security.Cryptography;
using System.Text;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class InvitationServiceTests
{
    [Fact]
    public void InitialWritePersistsDeliveryMetadata()
    {
        var row = new InvitationRecord(
            "invitation", "group", "person@example.com", "hash", "sent",
            "expires", "created", "updated", LastSentAt: "sent-at", MessageId: "message-id");

        var item = InvitationRepository.Write(row);

        Assert.Equal("sent-at", item["last_sent_at"].S);
        Assert.Equal("message-id", item["message_id"].S);
    }

    [Fact]
    public async Task FailedAcceptanceDoesNotCreateMembership()
    {
        const string token = "valid-token";
        var invitations = new FakeInvitations(token) { RejectAcceptance = true };
        var members = new FakeMembers();
        var subject = CreateSubject(invitations, members);

        var error = await Assert.ThrowsAsync<ApiException>(() => subject.AcceptAsync(
            "group",
            "invitation",
            new AcceptInvitationRequest(token),
            TestContext.Current.CancellationToken));

        Assert.Equal(409, error.StatusCode);
        Assert.Equal(0, members.CreateCalls);
        Assert.Null(invitations.CreatedMembership);
    }

    [Fact]
    public async Task AcceptanceDelegatesInvitationAndMembershipToOneAtomicWrite()
    {
        const string token = "valid-token";
        var invitations = new FakeInvitations(token);
        var members = new FakeMembers();
        var subject = CreateSubject(invitations, members);

        var result = await subject.AcceptAsync(
            "group",
            "invitation",
            new AcceptInvitationRequest(token),
            TestContext.Current.CancellationToken);

        Assert.True(result.Accepted);
        Assert.Equal(0, members.CreateCalls);
        Assert.NotNull(invitations.CreatedMembership);
        Assert.Equal("user", invitations.CreatedMembership.UserId);
        Assert.Equal("group", invitations.CreatedMembership.GroupId);
    }

    [Fact]
    public async Task AcceptanceAfterDrawCreatesPendingParticipantWithoutChangingDraw()
    {
        const string token = "valid-token";
        var invitations = new FakeInvitations(token);
        var subject = CreateSubject(invitations, new FakeMembers(), drawn: true);

        await subject.AcceptAsync(
            "group",
            "invitation",
            new AcceptInvitationRequest(token),
            TestContext.Current.CancellationToken);

        Assert.NotNull(invitations.CreatedMembership);
        Assert.False(invitations.CreatedMembership.IsParticipating);
    }

    [Fact]
    public async Task CoOrganizerCanManageInvitations()
    {
        var invitations = new FakeInvitations("token");
        var subject = CreateSubject(invitations, new FakeMembers(organizer: true));

        var result = await subject.ListAsync("group", TestContext.Current.CancellationToken);

        Assert.Empty(result);
    }

    [Fact]
    public async Task OrdinaryParticipantCannotManageInvitations()
    {
        var invitations = new FakeInvitations("token");
        var subject = CreateSubject(invitations, new FakeMembers(organizer: false));

        var error = await Assert.ThrowsAsync<ApiException>(() =>
            subject.ListAsync("group", TestContext.Current.CancellationToken));

        Assert.Equal(403, error.StatusCode);
    }

    private static InvitationService CreateSubject(
        FakeInvitations invitations,
        FakeMembers members,
        bool drawn = false) =>
        new(
            new FakeUser(),
            new FakeProfiles(),
            new FakeGroups(drawn),
            members,
            invitations,
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
        public string? Email => "person@example.com";
    }

    private sealed class FakeProfiles : IProfileRepository
    {
        public Task<ProfileRecord?> GetAsync(string userId, CancellationToken cancellationToken = default) =>
            Task.FromResult<ProfileRecord?>(new(userId, "Person", "now", "now"));
        public Task<ProfileRecord> UpsertAsync(string userId, string displayName, bool? nonEssentialEmailsEnabled = null, Consent? consent = null, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<ProfileRecord> SetAvatarKeyAsync(string userId, string? avatarKey, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string userId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class FakeGroups(bool drawn = false) : IGroupRepository
    {
        private readonly GroupRecord group = new(
            "group", "owner", "Exchange", "", null, null, null, "USD",
            PlanCode.Plus, "plus:entitlement", drawn ? GroupStatus.Drawn : GroupStatus.Open, "hash", [], "now", "now");

        public Task<GroupRecord?> GetAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<GroupRecord?>(group);
        public Task<GroupRecord> CreateAsync(GroupRecord group, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<GroupRecord> UpdateAsync(string groupId, IReadOnlyDictionary<string, AttributeValue> fields, GroupStatus? expectedStatus = null, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task CreateDrawAsync(string groupId, IReadOnlyDictionary<string, string> assignments, string actorUserId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<DrawRecord?> GetDrawAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task ResetDrawAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class FakeMembers(bool organizer = false) : IMembershipRepository
    {
        public int CreateCalls { get; private set; }
        // Not exercised here: this fake's service never reads an assignment.
        public Task SetGiftStageAsync(string memberId, string drawId, GiftStage stage, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
        public Task SetGiftReceivedAsync(string memberId, string drawId, bool received, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
        public Task ClearGiftProgressAsync(string memberId, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
        public Task SetWishClaimAsync(string memberId, string drawId, string wishId, WishClaimRecord claim, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
        public Task RemoveWishClaimAsync(string memberId, string drawId, string wishId, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
        public Task ClearWishClaimsAsync(string memberId, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
        public Task MarkAssignmentViewedAsync(string memberId, string drawId, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
        public Task<IReadOnlyList<MembershipRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<MembershipRecord>>([]);
        public Task<MembershipRecord?> GetByUserAndGroupAsync(string userId, string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<MembershipRecord?>(MembershipRepository.NewRecord(groupId, userId, "Person", organizer));
        public Task<MembershipRecord> CreateAsync(string groupId, string userId, string displayName, bool organizer, CancellationToken cancellationToken = default)
        {
            CreateCalls++;
            throw new InvalidOperationException("Managed invitations must use the atomic acceptance repository.");
        }
        public Task<MembershipRecord?> GetAsync(string memberId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<IReadOnlyList<MembershipRecord>> GetByUserAsync(string userId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdatePrivateAsync(string memberId, string wishlist, string avoidances, Address address, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdateParticipationAsync(string memberId, bool participating, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task AnonymizeAsync(string memberId, string pseudonym, string displayName, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string memberId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class FakeInvitations(string token) : IInvitationRepository
    {
        private readonly InvitationRecord invitation = new(
            "invitation", "group", "person@example.com", Hash(token), "sent",
            DateTimeOffset.UtcNow.AddDays(1).ToString("O"), "now", "now");

        public bool RejectAcceptance { get; init; }
        public MembershipRecord? CreatedMembership { get; private set; }

        public Task<InvitationRecord?> GetAsync(string invitationId, CancellationToken cancellationToken = default) =>
            Task.FromResult<InvitationRecord?>(invitation);
        public Task AcceptAndCreateMembershipAsync(string invitationId, string userId, MembershipRecord membership, CancellationToken cancellationToken = default)
        {
            if (RejectAcceptance) throw new TransactionCanceledException("conditional check failed");
            CreatedMembership = membership;
            return Task.CompletedTask;
        }
        public Task CreateAsync(InvitationRecord value, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<IReadOnlyList<InvitationRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<InvitationRecord>>([]);
        public Task UpdateAsync(string invitationId, string status, string? tokenHash, string? expiresAt, string? messageId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<string?> GetDeliveryStatusAsync(string? messageId, CancellationToken cancellationToken = default) => throw new NotImplementedException();

        private static string Hash(string value) =>
            Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));
    }

    private sealed class FakeEmail : ITransactionalEmailService
    {
        public Task<EmailSendResult> SendAsync(TransactionalEmail email, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
    }

    private sealed class FakeAudit : IAuditTrail
    {
        public Task RecordAsync(
            AuditAction action,
            string groupId,
            AuditTarget target,
            IReadOnlyDictionary<string, string>? metadata = null,
            string? organizationId = null,
            CancellationToken cancellationToken = default) =>
            Task.CompletedTask;
    }
}
