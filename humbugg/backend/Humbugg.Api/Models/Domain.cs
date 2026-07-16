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

public sealed record Profile(string UserId, string DisplayName, string CreatedAt, string UpdatedAt);

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

public sealed record SaveProfileRequest(string? DisplayName);
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

internal sealed record ProfileRecord(string UserId, string DisplayName, string CreatedAt, string UpdatedAt);
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
