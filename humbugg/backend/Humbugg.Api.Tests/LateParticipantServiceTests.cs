using Amazon.DynamoDBv2.Model;
using Humbugg.Api;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Humbugg.Api.Services.Email.Core;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class LateParticipantServiceTests
{
    [Fact]
    public void RepositoryBuildsOneConditionalTransactionForDrawAndMembership()
    {
        var proposal = new LateParticipantProposalRecord(
            "proposal",
            "late",
            "draw-v1",
            new Dictionary<string, string> { ["a"] = "late", ["late"] = "a" },
            ["a", "late"],
            "2026-07-20T18:00:00.0000000+00:00");

        var request = GroupRepository.LateProposalTransaction(
            "group",
            "draw-v1",
            proposal,
            "draw-v2",
            "2026-07-20T17:00:00.0000000+00:00",
            Fixture.Settings);

        Assert.Equal(2, request.TransactItems.Count);
        var drawUpdate = request.TransactItems[0].Update;
        var membershipUpdate = request.TransactItems[1].Update;
        Assert.Equal("draws", drawUpdate.TableName);
        Assert.Contains("draw_id = :expectedDraw", drawUpdate.ConditionExpression, StringComparison.Ordinal);
        Assert.Contains("late_proposal.proposal_id = :proposalId", drawUpdate.ConditionExpression, StringComparison.Ordinal);
        Assert.Contains("late_proposal.expires_at > :now", drawUpdate.ConditionExpression, StringComparison.Ordinal);
        Assert.Equal("draw-v2", drawUpdate.ExpressionAttributeValues[":newDraw"].S);
        Assert.Equal(proposal.Assignments, drawUpdate.ExpressionAttributeValues[":assignments"].M.ToDictionary(pair => pair.Key, pair => pair.Value.S));
        Assert.Equal("members", membershipUpdate.TableName);
        Assert.Contains("is_participating = :inactive", membershipUpdate.ConditionExpression, StringComparison.Ordinal);
        Assert.True(membershipUpdate.ExpressionAttributeValues[":active"].BOOL);
    }

    [Fact]
    public async Task PreviewPersistsOnlyAProposalAndReportsMinimumImpact()
    {
        var fixture = new Fixture();

        var result = await fixture.Subject.PreviewAsync(
            "group",
            "late",
            TestContext.Current.CancellationToken);

        Assert.Equal(2, result.AffectedParticipantCount);
        Assert.NotNull(fixture.Groups.Draw.LateProposal);
        Assert.Equal(0, fixture.Groups.ApplyCalls);
        Assert.False(fixture.Members.Item("late").IsParticipating);
        Assert.Empty(fixture.Email.Messages);
        Assert.Equal([AuditAction.LateParticipantRequested], fixture.Audit.Events.Select(item => item.Action));
    }

    [Fact]
    public async Task ConfirmationRequiresExplicitApproval()
    {
        var fixture = new Fixture();
        var preview = await fixture.Subject.PreviewAsync("group", "late", TestContext.Current.CancellationToken);

        var error = await Assert.ThrowsAsync<ApiException>(() => fixture.Subject.ConfirmAsync(
            "group",
            new(preview.ProposalId, Confirm: false),
            TestContext.Current.CancellationToken));

        Assert.Equal(400, error.StatusCode);
        Assert.Equal(0, fixture.Groups.ApplyCalls);
        Assert.Empty(fixture.Email.Messages);
    }

    [Fact]
    public async Task ExpiredOrWrongDrawProposalFailsWithoutMutationOrNotification()
    {
        var fixture = new Fixture();
        var preview = await fixture.Subject.PreviewAsync("group", "late", TestContext.Current.CancellationToken);
        fixture.Groups.MakeProposalStale();

        var error = await Assert.ThrowsAsync<ApiException>(() => fixture.Subject.ConfirmAsync(
            "group",
            new(preview.ProposalId, Confirm: true),
            TestContext.Current.CancellationToken));

        Assert.Equal(409, error.StatusCode);
        Assert.Equal(0, fixture.Groups.ApplyCalls);
        Assert.False(fixture.Members.Item("late").IsParticipating);
        Assert.Empty(fixture.Email.Messages);
    }

    [Fact]
    public async Task AtomicApplyActivatesMemberUsesProposalAndNotifiesExactlyAffectedContacts()
    {
        var fixture = new Fixture();
        var originalAssignments = fixture.Groups.Draw.Assignments;
        var preview = await fixture.Subject.PreviewAsync("group", "late", TestContext.Current.CancellationToken);
        var proposal = fixture.Groups.Draw.LateProposal!;

        var result = await fixture.Subject.ConfirmAsync(
            "group",
            new(preview.ProposalId, Confirm: true),
            TestContext.Current.CancellationToken);

        Assert.Equal("draw-v2", result.AssignmentVersion);
        Assert.Equal(proposal.Assignments, fixture.Groups.Draw.Assignments);
        Assert.NotEqual(originalAssignments, fixture.Groups.Draw.Assignments);
        Assert.True(fixture.Members.Item("late").IsParticipating);
        Assert.Equal(1, fixture.Groups.ApplyCalls);
        Assert.Equal(
            proposal.AffectedMemberIds.Order(StringComparer.Ordinal),
            fixture.Email.Messages.Select(message => fixture.MemberIdForEmail(message.ToAddress)).Order(StringComparer.Ordinal));
        Assert.All(fixture.Email.Messages, message => Assert.Contains("assignment_version=draw-v2", message.TextBody, StringComparison.Ordinal));
        Assert.Equal(
            [AuditAction.LateParticipantRequested, AuditAction.LateParticipantConfirmed, AuditAction.LateAssignmentsChanged],
            fixture.Audit.Events.Select(item => item.Action));
        Assert.All(
            fixture.Audit.Events,
            item => Assert.DoesNotContain(item.Metadata.Keys, key => key.Contains("assignment", StringComparison.OrdinalIgnoreCase)));
    }

    [Fact]
    public async Task FailedAtomicApplySendsNoNotifications()
    {
        var fixture = new Fixture { RejectApply = true };
        var preview = await fixture.Subject.PreviewAsync("group", "late", TestContext.Current.CancellationToken);

        var error = await Assert.ThrowsAsync<ApiException>(() => fixture.Subject.ConfirmAsync(
            "group",
            new(preview.ProposalId, Confirm: true),
            TestContext.Current.CancellationToken));

        Assert.Equal(409, error.StatusCode);
        Assert.False(fixture.Members.Item("late").IsParticipating);
        Assert.Empty(fixture.Email.Messages);
    }

    [Fact]
    public async Task ConfirmationRetryDoesNotReapplyAndUsesStableNotificationIds()
    {
        var fixture = new Fixture();
        var preview = await fixture.Subject.PreviewAsync("group", "late", TestContext.Current.CancellationToken);

        var first = await fixture.Subject.ConfirmAsync(
            "group",
            new(preview.ProposalId, Confirm: true),
            TestContext.Current.CancellationToken);
        var firstMessageIds = fixture.Email.Messages.Select(item => item.MessageId).ToArray();
        var retry = await fixture.Subject.ConfirmAsync(
            "group",
            new(preview.ProposalId, Confirm: true),
            TestContext.Current.CancellationToken);

        Assert.Equal(first, retry);
        Assert.Equal(1, fixture.Groups.ApplyCalls);
        Assert.Equal(firstMessageIds, fixture.Email.Messages.Skip(firstMessageIds.Length).Select(item => item.MessageId));
    }

    [Fact]
    public async Task MissingLegacyContactFailsBeforeTheProposalCanBeApplied()
    {
        var fixture = new Fixture();
        var preview = await fixture.Subject.PreviewAsync(
            "group",
            "late",
            TestContext.Current.CancellationToken);
        var affectedExistingMember = fixture.Groups.Draw.LateProposal!.AffectedMemberIds
            .Single(memberId => memberId != "late");
        fixture.Invitations.RemoveForUser(fixture.Members.Item(affectedExistingMember).UserId);
        fixture.User.Email = null;

        var error = await Assert.ThrowsAsync<ApiException>(() => fixture.Subject.ConfirmAsync(
            "group",
            new(preview.ProposalId, Confirm: true),
            TestContext.Current.CancellationToken));

        Assert.Equal(409, error.StatusCode);
        Assert.NotNull(fixture.Groups.Draw.LateProposal);
        Assert.Equal(0, fixture.Groups.ApplyCalls);
        Assert.Empty(fixture.Email.Messages);
    }

    [Fact]
    public async Task ObsoleteAssignmentVersionIsRejectedAndReturnsNoCachedAssignment()
    {
        var fixture = new Fixture();
        var service = fixture.CreateGroupService();

        var error = await Assert.ThrowsAsync<ApiException>(() => service.GetAssignmentAsync(
            "group",
            "draw-v0",
            TestContext.Current.CancellationToken));

        Assert.Equal(409, error.StatusCode);
        Assert.Contains("obsolete", error.Message, StringComparison.OrdinalIgnoreCase);
    }

    private sealed class Fixture
    {
        public Fixture()
        {
            Members = new FakeMembers();
            Groups = new FakeGroups(Members, () => RejectApply);
            Invitations = new FakeInvitations();
            Email = new FakeEmail();
            Audit = new FakeAudit();
            User = new FakeUser();
            Directory = new FakeAccountDirectory();
            Subject = new LateParticipantService(
                User,
                Groups,
                Members,
                Invitations,
                Directory,
                new MatchingService(),
                new PlanCatalog(new()),
                new TransactionalEmailTemplates(),
                Email,
                Audit,
                Settings);
        }

        public bool RejectApply { get; init; }
        public FakeGroups Groups { get; }
        public FakeUser User { get; }
        public FakeMembers Members { get; }
        public FakeInvitations Invitations { get; }
        public FakeAccountDirectory Directory { get; }
        public FakeEmail Email { get; }
        public FakeAudit Audit { get; }
        public LateParticipantService Subject { get; }

        internal static readonly HumbuggSettings Settings = new(
            "us-east-1", "us-east-1", "pool", "client",
            ["http://localhost:5173"], "http://localhost:5173", null,
            "profiles", "groups", "members", "draws", "audit", "analytics");

        public string MemberIdForEmail(string email) =>
            Members.Items.Single(item => $"{item.MemberId}@example.com" == email).MemberId;

        public GroupService CreateGroupService() => new(
            new FakeUser(),
            new FakeProfiles(),
            Groups,
            Members,
            new FakeWishes(),
            new FakeQuestions(),
            new FakeInvitations(),
            new MatchingService(),
            new PlanCatalog(new()),
            Audit,
            new FakeAnalytics(),
            Directory,
            new NoopEmail(),
            new TransactionalEmailTemplates(),
            NullLogger<GroupService>.Instance,
            Settings);
    }

    private sealed class FakeUser : ICurrentUser
    {
        public string UserId => "user-a";
        public string? Email { get; set; } = "a@example.com";
    }

    private sealed class FakeGroups(FakeMembers members, Func<bool> rejectApply) : IGroupRepository
    {
        private static readonly GroupRecord Group = new(
            "group", "user-a", "Exchange", "", null, null, null, "USD",
            PlanCode.Plus, "plus:paid", GroupStatus.Drawn, "hash", [], "now", "now");

        public DrawRecord Draw { get; private set; } = new(
            "group",
            "draw-v1",
            new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["a"] = "b",
                ["b"] = "c",
                ["c"] = "a"
            },
            "now",
            "user-a");
        public int ApplyCalls { get; private set; }

        public void MakeProposalStale() => Draw = Draw with { DrawId = "draw-other" };
        public Task<GroupRecord?> GetAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<GroupRecord?>(Group);
        public Task<DrawRecord?> GetDrawAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<DrawRecord?>(Draw);
        public Task SaveLateProposalAsync(string groupId, string expectedDrawId, LateParticipantProposalRecord proposal, CancellationToken cancellationToken = default)
        {
            if (Draw.DrawId != expectedDrawId) throw new ConditionalCheckFailedException("stale");
            Draw = Draw with { LateProposal = proposal };
            return Task.CompletedTask;
        }
        public Task<string> ApplyLateProposalAsync(string groupId, string expectedDrawId, LateParticipantProposalRecord proposal, CancellationToken cancellationToken = default)
        {
            if (rejectApply() || Draw.DrawId != expectedDrawId || Draw.LateProposal?.ProposalId != proposal.ProposalId)
                throw new TransactionCanceledException("stale");
            ApplyCalls++;
            members.Activate(proposal.MemberId);
            Draw = Draw with
            {
                DrawId = "draw-v2",
                Assignments = proposal.Assignments,
                LateProposal = null,
                LastLateProposalId = proposal.ProposalId,
                LastLateMemberId = proposal.MemberId,
                LastAffectedMemberIds = proposal.AffectedMemberIds
            };
            return Task.FromResult(Draw.DrawId);
        }
        public Task<GroupRecord> CreateAsync(GroupRecord group, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<GroupRecord> UpdateAsync(string groupId, IReadOnlyDictionary<string, AttributeValue> fields, GroupStatus? expectedStatus = null, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task CreateDrawAsync(string groupId, IReadOnlyDictionary<string, string> assignments, string actorUserId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task ResetDrawAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class FakeMembers : IMembershipRepository
    {
        public Task SetGiftStageAsync(string memberId, string drawId, GiftStage stage, CancellationToken cancellationToken = default)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            // Mirrors the repository, receipt clear included: moving the stage is only allowed while
            // nobody has confirmed receipt, so the write always leaves that unset.
            if (index >= 0)
                Items[index] = Items[index] with
                {
                    GiftStage = stage,
                    GiftStageAt = "now",
                    GiftReceivedAt = null,
                    GiftProgressDrawId = drawId,
                };
            return Task.CompletedTask;
        }
        public Task SetGiftReceivedAsync(string memberId, string drawId, bool received, CancellationToken cancellationToken = default)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            if (index >= 0)
                Items[index] = Items[index] with
                {
                    GiftReceivedAt = received ? "now" : null,
                    GiftProgressDrawId = drawId,
                };
            return Task.CompletedTask;
        }
        public Task ClearGiftProgressAsync(string memberId, CancellationToken cancellationToken = default)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            if (index >= 0)
                Items[index] = Items[index] with
                {
                    GiftStage = null,
                    GiftStageAt = null,
                    GiftReceivedAt = null,
                    GiftProgressDrawId = null,
                };
            return Task.CompletedTask;
        }
        public Task SetWishClaimAsync(string memberId, string drawId, string wishId, WishClaimRecord claim, CancellationToken cancellationToken = default)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            if (index < 0) return Task.CompletedTask;
            var current = Items[index];
            // Mirrors the repository: a map from an earlier draw is replaced, not merged into.
            var claims = current.WishClaimsDrawId == drawId && current.WishClaims is { } existing
                ? new Dictionary<string, WishClaimRecord>(existing, StringComparer.Ordinal)
                : new Dictionary<string, WishClaimRecord>(StringComparer.Ordinal);
            claims[wishId] = claim;
            Items[index] = current with { WishClaims = claims, WishClaimsDrawId = drawId };
            return Task.CompletedTask;
        }
        public Task RemoveWishClaimAsync(string memberId, string drawId, string wishId, CancellationToken cancellationToken = default)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            if (index < 0) return Task.CompletedTask;
            var current = Items[index];
            if (current.WishClaimsDrawId != drawId || current.WishClaims is not { } existing) return Task.CompletedTask;
            var claims = new Dictionary<string, WishClaimRecord>(existing, StringComparer.Ordinal);
            claims.Remove(wishId);
            Items[index] = current with { WishClaims = claims };
            return Task.CompletedTask;
        }
        public Task ClearWishClaimsAsync(string memberId, CancellationToken cancellationToken = default)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            if (index >= 0) Items[index] = Items[index] with { WishClaims = null, WishClaimsDrawId = null };
            return Task.CompletedTask;
        }
        public Task MarkAssignmentViewedAsync(string memberId, string drawId, CancellationToken cancellationToken = default)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            if (index >= 0) Items[index] = Items[index] with { AssignmentViewedDrawId = drawId };
            return Task.CompletedTask;
        }

        public List<MembershipRecord> Items { get; } =
        [
            Member("a", "user-a", organizer: true),
            Member("b", "user-b"),
            Member("c", "user-c"),
            Member("late", "user-late", participating: false)
        ];

        public MembershipRecord Item(string memberId) => Items.Single(item => item.MemberId == memberId);
        public void Activate(string memberId)
        {
            var index = Items.FindIndex(item => item.MemberId == memberId);
            Items[index] = Items[index] with { IsParticipating = true };
        }
        public Task<MembershipRecord?> GetByUserAndGroupAsync(string userId, string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<MembershipRecord?>(Items.SingleOrDefault(item => item.UserId == userId && item.GroupId == groupId));
        public Task<MembershipRecord?> GetAsync(string memberId, CancellationToken cancellationToken = default) =>
            Task.FromResult<MembershipRecord?>(Items.SingleOrDefault(item => item.MemberId == memberId));
        public Task<IReadOnlyList<MembershipRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<MembershipRecord>>(Items.Where(item => item.GroupId == groupId).ToList());
        public Task<IReadOnlyList<MembershipRecord>> GetByUserAsync(string userId, CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<MembershipRecord>>(Items.Where(item => item.UserId == userId).ToList());
        public Task<MembershipRecord> CreateAsync(string groupId, string userId, string displayName, bool organizer, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdatePrivateAsync(string memberId, string wishlist, string avoidances, Address address, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdateParticipationAsync(string memberId, bool participating, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdateOrganizerAsync(string memberId, bool organizer, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task AnonymizeAsync(string memberId, string pseudonym, string displayName, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string memberId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();

        private static MembershipRecord Member(
            string id,
            string userId,
            bool organizer = false,
            bool participating = true) =>
            new(id, "group", userId, id, organizer, participating, "wish", "", new Address(), "now", "now");
    }

    private sealed class FakeInvitations : IInvitationRepository
    {
        private readonly List<InvitationRecord> items =
        [
            Accepted("b", "user-b"),
            Accepted("c", "user-c"),
            Accepted("late", "user-late")
        ];

        public void RemoveForUser(string userId) => items.RemoveAll(item => item.AcceptedUserId == userId);
        public Task<IReadOnlyList<InvitationRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<InvitationRecord>>(items);
        public Task CreateAsync(InvitationRecord value, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<InvitationRecord?> GetAsync(string invitationId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task UpdateAsync(string invitationId, string status, string? tokenHash, string? expiresAt, string? messageId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task AcceptAndCreateMembershipAsync(string invitationId, string userId, MembershipRecord membership, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<string?> GetDeliveryStatusAsync(string? messageId, CancellationToken cancellationToken = default) => throw new NotImplementedException();

        private static InvitationRecord Accepted(string memberId, string userId) =>
            new(memberId, "group", $"{memberId}@example.com", "", "accepted", "future", "now", "now", "now", userId);
    }

    private sealed class FakeEmail : ITransactionalEmailService
    {
        public List<TransactionalEmail> Messages { get; } = [];
        public Task<EmailSendResult> SendAsync(TransactionalEmail email, CancellationToken cancellationToken = default)
        {
            Messages.Add(email);
            return Task.FromResult(new EmailSendResult(email.MessageId, email.Category, false, false, email.MessageId));
        }
    }

    private sealed class FakeAudit : IAuditTrail
    {
        public List<(AuditAction Action, IReadOnlyDictionary<string, string> Metadata)> Events { get; } = [];
        public Task RecordAsync(
            AuditAction action,
            string groupId,
            AuditTarget target,
            IReadOnlyDictionary<string, string>? metadata = null,
            string? organizationId = null,
            CancellationToken cancellationToken = default)
        {
            Events.Add((action, metadata ?? new Dictionary<string, string>()));
            return Task.CompletedTask;
        }
    }

    private sealed class FakeProfiles : IProfileRepository
    {
        public Task<ProfileRecord?> GetAsync(string userId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<ProfileRecord> UpsertAsync(string userId, string displayName, bool? nonEssentialEmailsEnabled = null, Consent? consent = null, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<ProfileRecord> SetAvatarKeyAsync(string userId, string? avatarKey, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string userId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class FakeAnalytics : IProductAnalytics
    {
        public Task TrackAsync(
            AnalyticsEventType type,
            PlanCode plan,
            string groupId,
            string idempotencyKey,
            IReadOnlyDictionary<string, string>? dimensions = null,
            CancellationToken cancellationToken = default) =>
            Task.CompletedTask;
    }
}
