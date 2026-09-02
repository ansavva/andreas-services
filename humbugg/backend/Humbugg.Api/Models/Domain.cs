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

// How far along a giver is on one wish (#130). Two states, not three: "planned" is a soft hold that
// stops the giver buying two of the same thing across sessions, "purchased" is done. There is no
// "sent" or "received" here — those are the exchange's milestones and belong to #132's roll-up,
// which counts these without ever naming who set them.
public enum WishClaimState { Planned, Purchased }

// How far along the gift itself is (#132), as distinct from any one wish on the list.
//
// The giver owns these three and the recipient owns "received", which is a SEPARATE field rather
// than a fourth stage. That is not a modelling nicety: a gift handed over at a party is never marked
// sent, and a single ordered enum would either refuse that or let a recipient overwrite the giver's
// record of what they did. Two fields, two owners, and the only ordering rule is the one that is
// actually true — a received gift was obviously bought.
public enum GiftStage { Choosing, Purchased, Sent }
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

/// <summary>
/// Plus branding for the INVITATION: what somebody sees while deciding whether to join.
/// </summary>
/// <remarks>
/// <see cref="Instructions"/> is not the same field as <c>GroupRecord.Instructions</c> and merging
/// them would be wrong in both directions. This one is invitation copy for people who are not
/// members yet, Plus-gated alongside the colours and the image it is written to sit with; that one
/// is how the exchange works, Free, and read by people who have already joined.
/// </remarks>
public sealed record ExchangeCustomization(
    string Greeting = "",
    string Instructions = "",
    string PrimaryColor = "#7C2D12",
    string AccentColor = "#F59E0B",
    string? ImageDataUrl = null);

public sealed record InvitationPreview(string GroupId, string ExchangeName, ExchangeCustomization Customization);
public sealed record ExchangeTemplate(
    string TemplateId, string Name, string ExchangeName, string Description,
    int SignupDeadlineDaysBeforeEvent, string WishlistPrompt,
    string ExclusionsPolicy, ReminderSettings ReminderPreferences, ExchangeCustomization Customization,
    IReadOnlyList<TemplateParticipant> PriorParticipants,
    string? SourceGroupId, string CreatedAt, string UpdatedAt);
public sealed record TemplateParticipant(string MemberId, string DisplayName, string Email);
public sealed record SaveTemplateRequest(string? Name, string? SourceGroupId);
public sealed record UpdateTemplateRequest(string? Name, string? ExchangeName, string? Description,
    int? SignupDeadlineDaysBeforeEvent, string? WishlistPrompt, string? ExclusionsPolicy,
    ReminderSettings? ReminderPreferences, UpdateCustomizationRequest? Customization);
public sealed record ApplyTemplateRequest(string? TargetGroupId, string? EventDate, IReadOnlyList<string>? PriorMemberIds);

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
    string UpdatedAt,
    // Whether this exchange posts its gifts. Off means the readiness dashboard does not count a
    // missing mailing address against anyone — an exchange handed over in person never needs one,
    // and nagging every participant for a field they should leave blank is worse than not asking.
    bool RequiresAddress = false);

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
    string? InviteUrl = null,
    ExchangeCustomization? Customization = null,
    bool RequiresAddress = false,
    /// <summary>How this exchange works, shown to people who have joined. See GroupRecord.</summary>
    string Instructions = "");

// ─── Organizer readiness (#133) ─────────────────────────────────────────────────────────────────
//
// The dashboard's whole state, computed on the server. The app renders these states and never
// re-derives one: "ready" has to mean the same thing in the roll-up, the participant row and the
// nudge list, and the only way to guarantee that is for exactly one place to decide it.
public enum ReadinessState
{
    // The participant has done it.
    Ready,
    // They have not, and this is what the organizer would nudge them about.
    Missing,
    // This exchange does not ask for it — a mailing address when gifts change hands in person.
    NotRequired,
    // The question does not apply: assignment views before the draw, anything for a non-participant.
    NotApplicable,
}

public enum ParticipantRole { Owner, CoOrganizer, Participant }

public enum NudgeReason { NoWishlist, NoAddress, AssignmentNotViewed, InvitationNotAccepted }

public sealed record ParticipantReadiness(
    string MemberId,
    string DisplayName,
    ParticipantRole Role,
    bool IsParticipating,
    ReadinessState Wishlist,
    // Counted so the organizer can tell an empty list from a full one without opening it. The wishes
    // themselves are never in this response: what someone asked for is between them and their giver.
    int WishCount,
    bool HasGeneralPreferences,
    ReadinessState Address,
    ReadinessState Assignment,
    IReadOnlyList<NudgeReason> Nudges);

/// <summary>An invitation that has been sent and not yet accepted. Plus-only in practice — a Free
/// exchange invites by link and has no invitation rows — but never gated here: an empty list is the
/// honest answer for Free, and a plan check would make the dashboard lie on the tier that has them.</summary>
public sealed record PendingInvitation(
    string InvitationId,
    string Email,
    InvitationStatus Status,
    string ExpiresAt,
    string? LastSentAt);

/// <summary>Aggregate gift progress — counts only, so it can never say who is giving to whom.
/// Null until gift tracking exists (#132). Null rather than three zeroes on purpose: zeroes read as
/// "nobody has bought anything yet", which is a different and false statement.</summary>
/// <summary>
/// The organizer's roll-up: counts, and nothing else.
/// </summary>
/// <remarks>
/// Cumulative, so a gift already sent still counts as purchased. An organizer reading "4 purchased,
/// 1 sent" would otherwise conclude four gifts are sitting in hallways when three are in the post.
/// Never a name, never a pairing, never a wish — the same rule the rest of the dashboard follows.
/// </remarks>
public sealed record GiftProgress(int Purchased, int Sent, int Received, int Total);

/// <summary>The caller's own gift status for their current assignment (#132).</summary>
public sealed record GiftStatus(
    GiftStage Stage,
    string? StageAt,
    bool Received,
    string? ReceivedAt,
    /// <summary>False once the recipient has confirmed receipt — the giver can no longer walk it back.</summary>
    bool CanChangeStage);

/// <summary>What the RECIPIENT sees and controls: whether they have said it arrived.</summary>
public sealed record GiftReceipt(bool Received, string? ReceivedAt);

public sealed record SetGiftStageRequest(string? Stage);
public sealed record SetGiftReceivedRequest(bool Received);

public sealed record ReadinessCounts(
    int Members,
    int Participating,
    int NotParticipating,
    int PendingInvitations,
    // Each of these three is out of Participating.
    int WishlistReady,
    int AddressReady,
    int AssignmentsViewed,
    // Participants with at least one outstanding item, plus every unaccepted invitation.
    int NeedsNudge);

public sealed record GroupReadiness(
    string GroupId,
    GroupStatus Status,
    PlanCode Plan,
    bool RequiresAddress,
    ReadinessCounts Counts,
    IReadOnlyList<ParticipantReadiness> Participants,
    IReadOnlyList<PendingInvitation> PendingInvitations,
    GiftProgress? GiftProgress);

// ─── Wishes ─────────────────────────────────────────────────────────────────────────────────────
//
// Two projections of the same stored row, and the split is deliberate rather than ceremonial.
// `Wish` is what an owner sees of their own list. `RecipientWish` is what their assigned giver sees.
// The seam is now load-bearing rather than anticipatory: `RecipientWish` carries `Claim` (#130) and
// `Wish` must never grow it, because a claim on your own list would tell you what your giver has
// already bought. Projecting both audiences from one record through one type would make that leak a
// one-line mistake. Neither type is ever the stored record.
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
    int Position,
    // The CALLER's own claim on this wish, or null. Never anyone else's — with one giver per
    // recipient there is only ever one, and reading a claim set by somebody else would be reading
    // who else is buying for this person, which is an assignment.
    WishClaim? Claim = null);

/// <summary>What the giver has decided about one wish. Visible only to that giver.</summary>
public sealed record WishClaim(WishClaimState State, int Quantity, string UpdatedAt);

public sealed record RecipientAssignment(
    string MemberId,
    string DisplayName,
    // Free-text general preferences. Structured wishes did not replace this field — see WishRecord —
    // so a list written before wishes existed still reaches the giver intact.
    string Wishlist,
    string Avoidances,
    Address Address,
    IReadOnlyList<RecipientWish> Wishes,
    // The CALLER's own gift status, never the recipient's opinion of it — the same rule as
    // RecipientWish.Claim. Null on the emergency reveal, which is not the giver reading their own.
    GiftStatus? Gift = null);

public sealed record RevealAssignment(Membership Giver, RecipientAssignment Recipient);

// ─── Anonymous questions (#131) ──────────────────────────────────────────────────────────────────
//
// A giver may ask their recipient about a gift without revealing who is asking. The anonymity is
// STRUCTURAL rather than a filter: no row anywhere in this feature stores the giver's member id.
// A message records which SIDE wrote it, and every request re-derives who the giver is from the
// draw. There is therefore no field to accidentally project, no id to leak through a URL, and
// nothing for a future endpoint to expose by returning "the whole row".
public enum QuestionAuthor
{
    /// <summary>The person giving the gift. Which person that is, is never stored.</summary>
    Giver,

    /// <summary>The person whose list it is. They own the thread and can end it.</summary>
    Recipient,
}

public sealed record QuestionMessage(
    string MessageId,
    QuestionAuthor Author,
    string Body,
    string CreatedAt);

/// <summary>
/// One conversation, as either side sees it. Identical for both — which is the point: if the two
/// projections differed, one of them would eventually differ by an identity.
/// </summary>
public sealed record QuestionThread(
    IReadOnlyList<QuestionMessage> Messages,
    /// <summary>The recipient has ended the conversation. Only they can lift it.</summary>
    bool Blocked,
    /// <summary>Whether THIS caller may send right now, with <see cref="BlockedReason"/> saying why not.</summary>
    bool CanSend,
    string? BlockedReason,
    int MessageLimit);

public sealed record SendQuestionRequest(string? Body);
public sealed record BlockQuestionsRequest(bool Blocked);

// Stored rows. `ThreadId` is `{groupId}:{drawId}:{recipientMemberId}` — deterministic, so a thread
// is addressed without a lookup, and self-invalidating, because a reset or a late-participant
// reassignment mints a new draw id and therefore a new, empty thread. The old conversation becomes
// unreachable by every route at once, which is the defined behaviour a reset needs: after it you may
// be buying for somebody else entirely.
//
// `MessageId` is an ISO-8601 UTC timestamp followed by a short random suffix, so the sort key orders
// chronologically without a second attribute and two messages in the same tick cannot collide.
//
// There is deliberately NO giver member id on this record.
internal sealed record QuestionMessageRecord(
    string ThreadId,
    string MessageId,
    string GroupId,
    string DrawId,
    string RecipientMemberId,
    QuestionAuthor Author,
    string Body,
    string CreatedAt);

/// <summary>The thread's own control row: whether the recipient has ended it.</summary>
internal sealed record QuestionThreadRecord(
    string ThreadId,
    string GroupId,
    string RecipientMemberId,
    bool Blocked,
    string UpdatedAt);
public sealed record RevealResponse(IReadOnlyList<RevealAssignment> Assignments);
public sealed record LateParticipantPreview(
    string ProposalId,
    string MemberId,
    int AffectedParticipantCount,
    string ExpiresAt);
public sealed record ConfirmLateParticipantRequest(string? ProposalId, bool Confirm);
public sealed record LateParticipantResult(
    string MemberId,
    int AffectedParticipantCount,
    string AssignmentVersion);
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
    string UpdatedAt,
    // The caller's own purchase claims for this exchange (#130) — data about their behaviour, so
    // the right of access covers it. Deliberately carries the wish id and NOT the recipient: the
    // export's standing rule is that it never names whom the caller was assigned to give to, and an
    // opaque id the caller has already seen does not name anyone.
    IReadOnlyList<ExportedWishClaim>? WishClaims = null);

public sealed record ExportedWishClaim(string WishId, WishClaimState State, int Quantity, string UpdatedAt);

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
    decimal? SpendingLimit,
    bool? RequiresAddress = null,
    string? Instructions = null,
    // The `updated_at` the client read before editing. Sent back so a save that would flatten
    // somebody else's change is refused instead. Optional: a caller flipping one switch from a value
    // it just computed has nothing to conflict with.
    string? ExpectedUpdatedAt = null);
/// <summary>Repeating an exchange (#136): what to carry over, and what the new one is called.</summary>
public sealed record RepeatExchangeRequest(
    string? Name,
    string? EventDate,
    string? SignupDeadline,
    bool CopyDetails = true,
    bool CopyExclusions = false);

/// <summary>
/// The new exchange, its one-time invitation link, and who was in the one it came from.
/// </summary>
/// <remarks>
/// <see cref="PriorParticipants"/> is a reminder of who to send the link to, not a guest list the
/// server acts on. Nobody is enrolled by repeating: they join with the link like anybody else, which
/// is what keeps last year's roster from silently becoming this year's.
/// </remarks>
public sealed record RepeatedExchange(
    GroupDetail Group,
    string InviteUrl,
    IReadOnlyList<string> PriorParticipants);

public sealed record UpdateCustomizationRequest(
    string? Greeting, string? Instructions, string? PrimaryColor, string? AccentColor, string? Image);
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
// Quantity is optional and defaults to the whole wish: "I am getting this" is the common case, and
// making a giver state a number to claim a quantity-1 item is friction for nothing.
public sealed record SetWishClaimRequest(string? State, int? Quantity);

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
    string UpdatedAt,
    ExchangeCustomization? Customization = null,
    bool RequiresAddress = false,
    // How this exchange works, in the organizer's own words, shown to people who have JOINED (#135).
    //
    // Distinct from ExchangeCustomization.Instructions, and the two must not be merged however
    // similar the names look. That one is INVITATION copy — read by somebody deciding whether to
    // join — and it is Plus-gated because it sits alongside the branding it is written for. This one
    // is Free and ungated, because an exchange that cannot tell its own participants where to bring
    // the gift does not work at any price.
    string Instructions = "");
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
    string UpdatedAt,
    // The draw this member has actually opened their assignment for, or null if they never have.
    // Stored as the draw id rather than a flag so it self-invalidates: a reset and a late-participant
    // reassignment both mint a new draw id, and everyone reverts to "has not looked" — which is the
    // truth, because the link they followed is the one the API now refuses as obsolete.
    string? AssignmentViewedDrawId = null,
    // This member's purchase claims, keyed by the WISH id on their recipient's list (#130).
    //
    // They live on the CLAIMANT's row, not on the wish, and that placement is the whole privacy
    // design. A wishlist owner never reads another member's private membership fields, so there is
    // no projection to get wrong and no endpoint to forget: the surprise is preserved by where the
    // data is, not by remembering to strip it. It also makes the row self-cleaning — claims die with
    // the membership, so the deletion sweep already covers them.
    IReadOnlyDictionary<string, WishClaimRecord>? WishClaims = null,
    // The draw those claims belong to, for the same self-invalidating reason as the field above. A
    // reset or a late-participant reassignment mints a new draw id and you may now be buying for
    // somebody else entirely; last draw's claims must not decorate this draw's list.
    string? WishClaimsDrawId = null,
    // How far along the gift this member is GIVING has got (#132). Owned by them.
    GiftStage? GiftStage = null,
    string? GiftStageAt = null,
    // When the person they are giving TO said it arrived. Written by that person, resolved through
    // the draw — so the recipient never learns whose row they wrote to, and the giver's own record
    // of what they did stays theirs.
    string? GiftReceivedAt = null,
    // Scope, for the same self-invalidating reason as the two fields above it: after a reset you may
    // be buying for somebody else, and last draw's progress is not this draw's.
    string? GiftProgressDrawId = null);

internal sealed record WishClaimRecord(WishClaimState State, int Quantity, string UpdatedAt);
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
    string CreatedBy,
    LateParticipantProposalRecord? LateProposal = null,
    string? LastLateProposalId = null,
    string? LastLateMemberId = null,
    IReadOnlyList<string>? LastAffectedMemberIds = null);
internal sealed record LateParticipantProposalRecord(
    string ProposalId,
    string MemberId,
    string ExpectedDrawId,
    IReadOnlyDictionary<string, string> Assignments,
    IReadOnlyList<string> AffectedMemberIds,
    string ExpiresAt);
public sealed record MinimalAssignmentResult(
    IReadOnlyDictionary<string, string> Assignments,
    IReadOnlyList<string> AffectedMemberIds);
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
