namespace Humbugg.Api.Models;

/// <summary>
/// The catalog of security- and privacy-relevant exchange actions that Humbugg audits.
/// The model deliberately covers actions that are not yet exposed as product features
/// (reminders, role changes, payment entitlement changes) so that auditing is standard
/// infrastructure the moment those features land. Every plan — Free, Plus, and Work — is
/// audited identically; auditing is never gated on a plan.
/// </summary>
public enum AuditAction
{
    GroupCreated,
    GroupUpdated,
    GroupDeleted,
    ParticipantJoined,
    ParticipantLeft,
    ParticipantRemoved,
    ParticipationChanged,
    ExclusionsChanged,
    InviteRotated,
    InvitationCreated,
    InvitationResent,
    InvitationAccepted,
    InvitationRevoked,
    DrawCreated,
    DrawReset,
    ReminderSent,
    RoleChanged,
    PaymentEntitlementChanged,
    AssignmentRevealed,
    ParticipantDataCleared,
    MembershipAnonymized,
    AccountDeleted,
}

/// <summary>
/// Identifies the object an audited action was performed on. The identifier is always a
/// server-side surrogate key (group id, member id, draw id) — never an invite secret, token,
/// address, or assignment content.
/// </summary>
public sealed record AuditTarget(string Type, string Id)
{
    public static AuditTarget Group(string groupId) => new("group", groupId);
    public static AuditTarget Member(string memberId) => new("member", memberId);
    public static AuditTarget Draw(string groupId) => new("draw", groupId);
    public static AuditTarget Invite(string groupId) => new("invite", groupId);
    public static AuditTarget Entitlement(string entitlementId) => new("entitlement", entitlementId);
    public static AuditTarget Role(string memberId) => new("role", memberId);
    public static AuditTarget Reminder(string groupId) => new("reminder", groupId);
    /// <summary>An account-scoped target. The id is always an anonymized pseudonym, never a raw Cognito subject.</summary>
    public static AuditTarget Account(string pseudonym) => new("account", pseudonym);
}

/// <summary>
/// A fully assembled, append-only audit record. Instances are produced by
/// <see cref="Humbugg.Api.Services.IAuditTrail"/> after redaction and are only ever written,
/// never updated or deleted, through the application.
/// </summary>
public sealed record AuditEvent(
    string GroupId,
    string EventId,
    AuditAction Action,
    string ActorUserId,
    string TargetType,
    string TargetId,
    string? OrganizationId,
    string CorrelationId,
    string CreatedAt,
    IReadOnlyDictionary<string, string> Metadata);
