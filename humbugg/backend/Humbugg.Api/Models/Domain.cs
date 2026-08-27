using System.Text.Json.Serialization;

namespace Humbugg.Api.Models;

public enum GroupStatus { Open, Drawn }

// A wish is one entry on a participant's list. `Custom` covers anything that is not a purchasable
// product — "a day out", "learn to bake" — and is the fallback when a URL cannot be resolved into a
// product (#129), so a failed extraction degrades to a usable wish rather than blocking the user.
public enum WishKind { Product, Custom, Experience, Charity }

// Ordering hint for the giver, not a sort key: the list's own order is `position`, which the owner
// controls. Priority says how much the wish is wanted, which is a different question from where it sits.
public enum WishPriority { Low, Normal, High }
public enum PlanCode { Free, Plus, Work }
public enum BillingCadence { Free, OneTime, Annual }

public sealed record PlanDefinition(
    PlanCode Code,
    string Name,
    int ParticipantLimit,
    bool MarketedAsUnlimited,
    long PriceCents,
    string Currency,
    BillingCadence BillingCadence,
    string? ProductId = null,
    string? PriceId = null);

public sealed record Address(
    string? Line1 = null,
    string? Line2 = null,
    string? City = null,
    string? Region = null,
    string? PostalCode = null,
    string? Country = null);

// Recorded proof that a user actively agreed to the published Terms of Service and Privacy Policy at
// signup (GDPR Art. 7 — demonstrable consent). Version mirrors POLICY_VERSION in the frontend policy
// config so the record stays in sync with the published policies; AcceptedAt is a UTC ISO-8601
// timestamp of the moment the user ticked the consent box.
public sealed record Consent(string Version, string AcceptedAt);

public sealed record Profile(
    string UserId,
    string DisplayName,
    string CreatedAt,
    string UpdatedAt,
    string? AvatarUrl = null,
    // Governs whether Humbugg sends this account non-essential product email (reminders,
    // group-activity notifications, product news). Essential mail always sends. Default on.
    bool NonEssentialEmailsEnabled = true,
    // Terms/Privacy consent captured at signup. Null only for rows written before consent was recorded.
    Consent? Consent = null);

public sealed record Membership(
    string MemberId,
    string DisplayName,
    bool IsOrganizer,
    bool IsParticipating,
    string? Wishlist = null,
    string? Avoidances = null,
    Address? Address = null,
    bool IsOwner = false,
    bool IsReady = false);

public sealed record GroupSummary(
    string GroupId,
    string Name,
    GroupStatus Status,
    string? EventDate,
    decimal? SpendingLimit,
    string Currency,
    PlanCode Plan,
    int ParticipantLimit,
    bool IsOrganizer,
    bool IsOwner,
    string CreatedAt,
    string UpdatedAt);

public sealed record GroupDetail(
    string GroupId,
    string Name,
    GroupStatus Status,
    string? EventDate,
    decimal? SpendingLimit,
    string Currency,
    PlanCode Plan,
    int ParticipantLimit,
    bool IsOrganizer,
    bool IsOwner,
    string CreatedAt,
    string UpdatedAt,
    string Description,
    string? SignupDeadline,
    IReadOnlyList<string[]> Exclusions,
    IReadOnlyList<Membership> Members,
    string? InviteUrl = null);

// ─── Wishes ─────────────────────────────────────────────────────────────────────────────────────
//
// Two projections of the same stored row, and the split is deliberate rather than ceremonial.
// `Wish` is what an owner sees of their own list. `RecipientWish` is what their assigned giver sees.
// They carry the same fields today, which is exactly why the seam has to exist now: #130 adds
// purchase claims, which every gift viewer may see and the owner may never see, and #132 adds gift
// progress. Projecting both from one record through one type would make that leak a one-line
// mistake. Neither type is ever the stored record.
public sealed record Wish(
    string WishId,
    WishKind Kind,
    string Title,
    string? Url,
    string? ImageUrl,
    long? PriceCents,
    string? Currency,
    int Quantity,
    WishPriority Priority,
    string? Details,
    int Position,
    string CreatedAt,
    string UpdatedAt);

// The giver's view. Deliberately has no CreatedAt/UpdatedAt: when a recipient last edited their list
// is the recipient's business, and an edit timestamp moving is a signal about their behaviour.
public sealed record RecipientWish(
    string WishId,
    WishKind Kind,
    string Title,
    string? Url,
    string? ImageUrl,
    long? PriceCents,
    string? Currency,
    int Quantity,
    WishPriority Priority,
    string? Details,
    int Position);

public sealed record RecipientAssignment(
    string MemberId,
    string DisplayName,
    // Free-text general preferences. Structured wishes did not replace this field — see WishRecord —
    // so a list written before wishes existed still reaches the giver intact.
    string Wishlist,
    string Avoidances,
    Address Address,
    IReadOnlyList<RecipientWish> Wishes);

public sealed record RevealAssignment(Membership Giver, RecipientAssignment Recipient);
public sealed record RevealResponse(IReadOnlyList<RevealAssignment> Assignments);
public sealed record InviteResponse(string InviteUrl);
public enum InvitationStatus { Sent, Delivered, Bounced, Accepted, Expired, Revoked }
public sealed record ManagedInvitation(string InvitationId, string Email, InvitationStatus Status, string ExpiresAt, string? AcceptedAt, string? LastSentAt);
public sealed record CreateInvitationsRequest(IReadOnlyList<string>? Emails);
public sealed record CreateInvitationsResponse(IReadOnlyList<ManagedInvitation> Invitations);
public sealed record AcceptInvitationRequest(string? Token, bool ConfirmAddressMismatch = false);
public sealed record AcceptInvitationResponse(string GroupId, bool Accepted);
public enum ReminderState { Active, Paused, Stopped }
public enum ReminderRule { UnacceptedInvitation, IncompleteReadiness }
public sealed record UpdateReminderSettingsRequest(
    ReminderState State,
    bool RemindUnacceptedInvitations,
    bool RemindIncompleteReadiness,
    int IntervalDays = 3,
    int QuietStartUtcHour = 9,
    int QuietEndUtcHour = 20);
public sealed record ManualReminderRequest(string? InvitationId, ReminderRule Rule);
public sealed record ReminderSettings(
    ReminderState State,
    bool RemindUnacceptedInvitations,
    bool RemindIncompleteReadiness,
    int IntervalDays,
    int QuietStartUtcHour,
    int QuietEndUtcHour);
public sealed record ReminderHistoryItem(
    string ReminderId,
    ReminderRule Rule,
    string InvitationId,
    string Status,
    string CreatedAt);
public sealed record ReminderOverview(
    ReminderSettings Settings,
    string? NextScheduledAt,
    IReadOnlyList<ReminderHistoryItem> RecentHistory);

// ─── Self-service data export (GDPR right of access / portability, issue #189) ──────────────────
//
// A portable, machine-readable snapshot of the CALLER'S OWN personal data. It contains only data the
// requesting user authored or that identifies them; it never includes another member's wishlist,
// avoidances, address, or draw assignment, and never reveals who the caller was assigned to give to
// (that recipient's data belongs to the recipient, not the caller).
public sealed record DataExport(
    DataExportMetadata Metadata,
    ExportedProfile Profile,
    IReadOnlyList<ExportedMembership> Memberships);

public sealed record DataExportMetadata(
    string GeneratedAt,
    string FormatVersion,
    string SubjectUserId,
    IReadOnlyList<string> Notes);

public sealed record ExportedProfile(
    string UserId,
    string? DisplayName,
    string? Email,
    string? CreatedAt,
    string? UpdatedAt,
    // Reserved for the extended-profile fields other issues add, exported once they land so the export
    // stays the single "everything we hold about you" view: avatar (#186), non-essential-email
    // preference (#187), and recorded Terms/Privacy consent (#188). Null until those ship.
    string? Avatar = null,
    bool? NonEssentialEmailsEnabled = null,
    ExportedConsent? Consent = null);

public sealed record ExportedConsent(string PolicyVersion, string AgreedAt);

public sealed record ExportedMembership(
    string GroupId,
    string GroupName,
    GroupStatus GroupStatus,
    string MemberId,
    string Role,
    bool IsParticipating,
    string? Wishlist,
    string? Avoidances,
    Address? Address,
    // The caller's own wishes. Personal data they authored, so the export must carry it (#189).
    IReadOnlyList<Wish> Wishes,
    string JoinedAt,
    string UpdatedAt);

public sealed record SaveProfileRequest(
    string? DisplayName,
    bool? NonEssentialEmailsEnabled = null,
    ConsentInput? Consent = null);
// Client-supplied consent captured at the signup checkbox: the accepted policy version and the UTC
// ISO-8601 timestamp of the tick. Validated and required the first time a profile is created.
public sealed record ConsentInput(string? Version, string? AcceptedAt);
// Avatar upload payload: a data URL ("data:image/png;base64,...") or bare base64. Sent as JSON so
// the image flows through the same API Gateway/Lambda path as every other request; the raw decoded
// size is capped well under the 6 MB Lambda payload limit (see AvatarImage.MaxBytes).
public sealed record UploadAvatarRequest(string? Image);
public sealed record CreateGroupRequest(
    string? Name,
    string? Description,
    string? EventDate,
    string? SignupDeadline,
    decimal? SpendingLimit);
public sealed record UpdateGroupRequest(
    string? Name,
    string? Description,
    string? EventDate,
    string? SignupDeadline,
    decimal? SpendingLimit);
public sealed record JoinGroupRequest(string? InviteToken);
public sealed record UpdateMembershipRequest(string? Wishlist, string? Avoidances, Address? Address);
public sealed record ParticipationRequest(bool? IsParticipating);
public sealed record OrganizerRoleRequest(bool? IsOrganizer);
public sealed record ExclusionsRequest(IReadOnlyList<string[]>? Exclusions);
public sealed record RevealRequest(string? Reason);

public sealed record CreateWishRequest(
    string? Kind,
    string? Title,
    string? Url,
    string? ImageUrl,
    long? PriceCents,
    string? Currency,
    int? Quantity,
    string? Priority,
    string? Details);

// Every field is nullable and absence means "leave alone", so a partial edit cannot blank a field
// the caller never mentioned. Clearing an optional field is an explicit empty string.
public sealed record UpdateWishRequest(
    string? Kind,
    string? Title,
    string? Url,
    string? ImageUrl,
    long? PriceCents,
    string? Currency,
    int? Quantity,
    string? Priority,
    string? Details);

public sealed record ReorderWishesRequest(IReadOnlyList<string>? WishIds);

internal sealed record ProfileRecord(
    string UserId,
    string DisplayName,
    string CreatedAt,
    string UpdatedAt,
    string? AvatarKey = null,
    bool NonEssentialEmailsEnabled = true,
    string? ConsentVersion = null,
    string? ConsentAcceptedAt = null);
internal sealed record GroupRecord(
    string GroupId,
    string OwnerUserId,
    string Name,
    string Description,
    string? EventDate,
    string? SignupDeadline,
    long? SpendingLimitCents,
    string Currency,
    PlanCode Plan,
    string? EntitlementId,
    GroupStatus Status,
    string InviteHash,
    IReadOnlyList<string[]> Exclusions,
    string CreatedAt,
    string UpdatedAt);
internal sealed record MembershipRecord(
    string MemberId,
    string GroupId,
    string UserId,
    string DisplayName,
    bool IsOrganizer,
    bool IsParticipating,
    string Wishlist,
    string Avoidances,
    Address Address,
    string CreatedAt,
    string UpdatedAt);
// Stored row. `MemberId` is the partition key and `WishId` the sort key, so listing one member's
// wishes is a Query and never a Scan, and every single-item operation must name the owning member —
// ownership is enforced by the key itself rather than by a check someone can forget.
//
// GroupId and UserId are stored although MemberId already implies both. They make ownership and the
// owning list explicit on the row, which is what the audit trail and the deletion sweep read, and
// what keeps a row interpretable without joining back to the membership table.
internal sealed record WishRecord(
    string MemberId,
    string WishId,
    string GroupId,
    string UserId,
    WishKind Kind,
    string Title,
    string Url,
    string ImageUrl,
    long? PriceCents,
    string Currency,
    int Quantity,
    WishPriority Priority,
    string Details,
    int Position,
    string CreatedAt,
    string UpdatedAt);

internal sealed record DrawRecord(
    string GroupId,
    string DrawId,
    IReadOnlyDictionary<string, string> Assignments,
    string CreatedAt,
    string CreatedBy);
internal sealed record InvitationRecord(
    string InvitationId, string GroupId, string Email, string TokenHash, string Status,
    string ExpiresAt, string CreatedAt, string UpdatedAt, string? AcceptedAt = null,
    string? AcceptedUserId = null, string? LastSentAt = null, string? MessageId = null);
internal sealed record ReminderConfigurationRecord(
    string GroupId,
    ReminderState State,
    bool RemindUnacceptedInvitations,
    bool RemindIncompleteReadiness,
    int IntervalDays,
    int QuietStartUtcHour,
    int QuietEndUtcHour,
    string? NextScheduledAt,
    string? LastManualAt,
    string UpdatedAt);

public class ApiException(int statusCode, string code, string message) : Exception(message)
{
    public int StatusCode { get; } = statusCode;
    public string Code { get; } = code;
    public static ApiException BadRequest(string message) => new(400, "bad_request", message);
    public static ApiException Forbidden(string message) => new(403, "forbidden", message);
    public static ApiException PaymentRequired(string message) => new(402, "plus_required", message);
    public static ApiException NotFound(string message) => new(404, "not_found", message);
    public static ApiException Conflict(string message) => new(409, "conflict", message);
}
