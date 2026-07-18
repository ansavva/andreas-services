using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class AuditTrailTests
{
    // ─── Redaction guarantee ────────────────────────────────────────────────

    [Fact]
    public void RedactionReplacesSensitiveKeysWithPlaceholder()
    {
        var redacted = AuditRedaction.Redact(new Dictionary<string, string>
        {
            ["reason"] = "member left the exchange",
            ["shipping_address"] = "10 Downing Street",
            ["invite_secret"] = "abc",
            ["assignment"] = "user-a -> user-b",
            ["recipient_wishlist"] = "a bicycle",
            ["email"] = "santa@example.com"
        });

        Assert.Equal("member left the exchange", redacted["reason"]);
        Assert.Equal(AuditRedaction.Placeholder, redacted["shipping_address"]);
        Assert.Equal(AuditRedaction.Placeholder, redacted["invite_secret"]);
        Assert.Equal(AuditRedaction.Placeholder, redacted["assignment"]);
        Assert.Equal(AuditRedaction.Placeholder, redacted["recipient_wishlist"]);
        Assert.Equal(AuditRedaction.Placeholder, redacted["email"]);
    }

    [Fact]
    public void RedactionReplacesSecretLookingValuesUnderBenignKeys()
    {
        var redacted = AuditRedaction.Redact(new Dictionary<string, string>
        {
            ["note"] = "https://humbugg.com/join/group-1#invite=xU7yQ2",
            ["detail"] = "kR3nQ9zX1mP4wL7vB2cD8fG5hJ0tY6sA",
            ["count"] = "3"
        });

        Assert.Equal(AuditRedaction.Placeholder, redacted["note"]);
        Assert.Equal(AuditRedaction.Placeholder, redacted["detail"]);
        Assert.Equal("3", redacted["count"]);
    }

    [Fact]
    public void RedactionOfNullOrEmptyMetadataIsEmpty() =>
        Assert.Empty(AuditRedaction.Redact(null));

    // ─── Required event content: actor, action, target, scope, time, correlation ─

    [Fact]
    public async Task RecordedEventCapturesActorActionTargetTimeAndCorrelation()
    {
        var repository = new CapturingRepository();
        var subject = new AuditTrail(new FakeUser("actor-1"), new FakeCorrelation("corr-99"), repository);

        await subject.RecordAsync(AuditAction.DrawCreated, "group-1", AuditTarget.Draw("group-1"),
            new Dictionary<string, string> { ["participant_count"] = "5" }, cancellationToken: TestContext.Current.CancellationToken);

        var saved = Assert.Single(repository.Saved);
        Assert.Equal(AuditAction.DrawCreated, saved.Action);
        Assert.Equal("actor-1", saved.ActorUserId);
        Assert.Equal("group-1", saved.GroupId);
        Assert.Equal("draw", saved.TargetType);
        Assert.Equal("group-1", saved.TargetId);
        Assert.Equal("corr-99", saved.CorrelationId);
        Assert.False(string.IsNullOrWhiteSpace(saved.CreatedAt));
        Assert.Equal("5", saved.Metadata["participant_count"]);
    }

    [Fact]
    public async Task RecordedMetadataIsRedactedBeforePersistence()
    {
        var repository = new CapturingRepository();
        var subject = new AuditTrail(new FakeUser("actor-1"), new FakeCorrelation("corr"), repository);

        await subject.RecordAsync(AuditAction.AssignmentRevealed, "group-1", AuditTarget.Group("group-1"),
            new Dictionary<string, string> { ["recipient_address"] = "10 Downing Street", ["reason"] = "audit" },
            cancellationToken: TestContext.Current.CancellationToken);

        var saved = Assert.Single(repository.Saved);
        Assert.Equal(AuditRedaction.Placeholder, saved.Metadata["recipient_address"]);
        Assert.Equal("audit", saved.Metadata["reason"]);
    }

    // ─── Audit writes cannot silently fail for protected actions ─────────────

    [Fact]
    public async Task ProtectedWriteFailurePropagatesAndIsNotSwallowed()
    {
        var subject = new AuditTrail(new FakeUser("actor-1"), new FakeCorrelation("corr"), new ThrowingRepository());

        await Assert.ThrowsAsync<ConditionalCheckFailedException>(() => subject.RecordAsync(
            AuditAction.GroupDeleted, "group-1", AuditTarget.Group("group-1"),
            cancellationToken: TestContext.Current.CancellationToken));
    }

    // ─── Append-only: the repository exposes no update or delete path ────────

    [Fact]
    public void AuditRepositoryIsAppendOnly()
    {
        var methods = typeof(IAuditRepository).GetMethods().Select(method => method.Name).ToArray();
        Assert.Equal(["AppendAsync"], methods);
        Assert.DoesNotContain(methods, name =>
            name.Contains("Update", StringComparison.Ordinal) || name.Contains("Delete", StringComparison.Ordinal));
    }

    // ─── The audit model covers every required action, on every plan ─────────

    [Fact]
    public void AuditModelCoversEveryRequiredAction()
    {
        var actions = Enum.GetValues<AuditAction>();
        AuditAction[] required =
        [
            AuditAction.GroupCreated, AuditAction.GroupDeleted,
            AuditAction.ParticipantJoined, AuditAction.ParticipantLeft, AuditAction.ParticipantRemoved, AuditAction.ParticipationChanged,
            AuditAction.ExclusionsChanged, AuditAction.DrawCreated, AuditAction.DrawReset,
            AuditAction.ReminderSent, AuditAction.RoleChanged, AuditAction.PaymentEntitlementChanged,
            AuditAction.AssignmentRevealed
        ];
        Assert.All(required, action => Assert.Contains(action, actions));
    }

    [Theory]
    [InlineData(AuditAction.GroupCreated, "group_created")]
    [InlineData(AuditAction.PaymentEntitlementChanged, "payment_entitlement_changed")]
    [InlineData(AuditAction.AssignmentRevealed, "assignment_revealed")]
    public void ActionsSerializeToSnakeCaseWireForm(AuditAction action, string expected) =>
        Assert.Equal(expected, AuditRepository.Wire(action));

    private sealed class CapturingRepository : IAuditRepository
    {
        public List<AuditEvent> Saved { get; } = [];
        public Task AppendAsync(AuditEvent auditEvent, CancellationToken cancellationToken = default)
        {
            Saved.Add(auditEvent);
            return Task.CompletedTask;
        }
    }

    private sealed class ThrowingRepository : IAuditRepository
    {
        public Task AppendAsync(AuditEvent auditEvent, CancellationToken cancellationToken = default) =>
            throw new ConditionalCheckFailedException("write rejected");
    }

    private sealed class FakeUser(string userId) : ICurrentUser { public string UserId => userId; }
    private sealed class FakeCorrelation(string id) : IRequestCorrelation { public string CorrelationId => id; }
}
