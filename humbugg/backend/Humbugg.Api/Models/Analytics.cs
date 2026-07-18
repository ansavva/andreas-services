namespace Humbugg.Api.Models;

/// <summary>
/// The product-analytics funnel: the ordered set of milestones Humbugg measures to tell
/// whether an exchange is created, drawn, and completed, and whether paid plans convert and
/// retain. This is a <b>separate stream</b> from the security <see cref="AuditAction"/> audit
/// trail — analytics answers "does the product work?" with aggregate counts, never "who did
/// what to whom?". Analytics events deliberately carry no wishlist text, addresses, email
/// addresses, invite tokens, or assignment contents; enforcement lives in
/// <see cref="Humbugg.Api.Services.AnalyticsDimensions"/>.
/// </summary>
public enum AnalyticsEventType
{
    GroupCreated,
    InviteSent,
    ParticipantJoined,
    ParticipantReady,
    DrawCompleted,
    AssignmentViewed,
    GiftSent,
    GiftReceived,
    PlanUpgraded,
    SubscriptionRenewed,
    SubscriptionCancelled,
    RepeatExchangeCreated,
}

/// <summary>
/// A single, privacy-safe analytics measurement. Instances are only ever produced by
/// <see cref="Humbugg.Api.Services.IProductAnalytics"/> after the dimensions have passed through
/// <see cref="Humbugg.Api.Services.AnalyticsDimensions.Sanitize"/>, so a fully built event can
/// never contain a prohibited field.
/// </summary>
/// <param name="EventType">The funnel milestone this event records.</param>
/// <param name="Plan">The plan in effect (<see cref="PlanCode"/>) — recorded on every event.</param>
/// <param name="GroupId">
/// The group surrogate key. It correlates events for the same exchange so funnel ratios
/// (create → invite → join → draw) can be computed. It is never an invite token, address, or
/// assignment — only the server-side group id.
/// </param>
/// <param name="IdempotencyKey">
/// The deterministic dedup key for this transition. Re-emitting the same key is a no-op at the
/// sink, so retries and double-clicks never inflate counts.
/// </param>
/// <param name="OccurredAt">ISO-8601 UTC timestamp the event was recorded.</param>
/// <param name="Dimensions">Allow-listed aggregate dimensions (counts, plan codes, day spans).</param>
public sealed record AnalyticsEvent(
    AnalyticsEventType EventType,
    PlanCode Plan,
    string GroupId,
    string IdempotencyKey,
    string OccurredAt,
    IReadOnlyDictionary<string, string> Dimensions);
