using System.Text.Json.Serialization;

namespace Humbugg.Api.Models;

public enum GroupStatus { Open, Drawn }
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

public sealed record Profile(
    string UserId,
    string DisplayName,
    string CreatedAt,
    string UpdatedAt,
    string? AvatarUrl = null,
    // Governs whether Humbugg sends this account non-essential product email (reminders,
    // group-activity notifications, product news). Essential mail always sends. Default on.
    bool NonEssentialEmailsEnabled = true);

public sealed record Membership(
    string MemberId,
    string DisplayName,
    bool IsOrganizer,
    bool IsParticipating,
    string? Wishlist = null,
    string? Avoidances = null,
    Address? Address = null);

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
    string CreatedAt,
    string UpdatedAt,
    string Description,
    string? SignupDeadline,
    IReadOnlyList<string[]> Exclusions,
    IReadOnlyList<Membership> Members,
    string? InviteUrl = null);

public sealed record RecipientAssignment(
    string MemberId,
    string DisplayName,
    string Wishlist,
    string Avoidances,
    Address Address);

public sealed record RevealAssignment(Membership Giver, RecipientAssignment Recipient);
public sealed record RevealResponse(IReadOnlyList<RevealAssignment> Assignments);
public sealed record InviteResponse(string InviteUrl);

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
    string JoinedAt,
    string UpdatedAt);

public sealed record SaveProfileRequest(string? DisplayName, bool? NonEssentialEmailsEnabled = null);
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
public sealed record ExclusionsRequest(IReadOnlyList<string[]>? Exclusions);
public sealed record RevealRequest(string? Reason);

internal sealed record ProfileRecord(
    string UserId,
    string DisplayName,
    string CreatedAt,
    string UpdatedAt,
    string? AvatarKey = null,
    bool NonEssentialEmailsEnabled = true);
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
internal sealed record DrawRecord(
    string GroupId,
    string DrawId,
    IReadOnlyDictionary<string, string> Assignments,
    string CreatedAt,
    string CreatedBy);

public class ApiException(int statusCode, string code, string message) : Exception(message)
{
    public int StatusCode { get; } = statusCode;
    public string Code { get; } = code;
    public static ApiException BadRequest(string message) => new(400, "bad_request", message);
    public static ApiException Forbidden(string message) => new(403, "forbidden", message);
    public static ApiException NotFound(string message) => new(404, "not_found", message);
    public static ApiException Conflict(string message) => new(409, "conflict", message);
}
