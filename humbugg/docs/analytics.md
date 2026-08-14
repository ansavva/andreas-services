# Humbugg product analytics

This document defines Humbugg's **privacy-safe product analytics**: the funnel we measure,
the events we emit, the dimensions we are allowed to record, the metrics we compute, and the
minimal internal path for reading them. Analytics answers one question — *does Humbugg create
successful exchanges, and do paid plans convert and retain?* — **without ever recording private
gift data**.

Analytics is a **separate stream** from the security [audit trail](../infra/README.md#audit-trail).
The audit trail answers "who did what to whom" for security and privacy accountability; analytics
answers "does the product work" with aggregate counts. They share only the redaction utilities in
`Humbugg.Api/Services/AuditTrail.cs` (`AuditRedaction`).

## The conversion funnel

Events, in funnel order. Each is emitted **server-side** from `GroupService`
(`Humbugg.Api/Services/GroupService.cs`) via `IProductAnalytics`
(`Humbugg.Api/Services/ProductAnalytics.cs`).

| # | Event (`event_type`) | Emitted when | Idempotency key | Aggregate dimensions |
|---|---|---|---|---|
| 1 | `group_created` | An organizer creates a group | `group_created:{groupId}` | `is_repeat` |
| 2 | `invite_sent` | A group's invite is first created / rotated | `invite_sent:{groupId}` | — |
| 3 | `participant_joined` | A member joins via a valid invite | `participant_joined:{memberId}` | `member_count` |
| 4 | `participant_ready` | A member saves a non-empty wish list | `participant_ready:{memberId}` | — |
| 5 | `draw_completed` | The organizer runs the draw | `draw_completed:{groupId}` | `participant_count`, `days_to_draw` |
| 6 | `assignment_viewed` | A member views their assignment | `assignment_viewed:{memberId}` | — |
| 7 | `gift_sent` | A giver marks a gift as sent | `gift_sent:{memberId}` | — |
| 8 | `gift_received` | A recipient marks a gift as received | `gift_received:{memberId}` | — |
| 9 | `plan_upgraded` | A group upgrades Free → Plus/Work | `plan_upgraded:{groupId}` | `plan_from`, `plan_to`, `billing_cadence` |
| 10 | `subscription_renewed` | A Work subscription renews | `subscription_renewed:{groupId}:{period}` | `billing_cadence` |
| 11 | `subscription_cancelled` | A subscription is cancelled | `subscription_cancelled:{groupId}` | `billing_cadence` |
| 12 | `repeat_exchange_created` | An organizer creates a further exchange | `repeat_exchange:{groupId}` | — |

Events 1–6 and 12 are wired today. Events 7–11 (`gift_sent`, `gift_received`, and the payment
events) are **defined and ready to emit** the moment the gift-fulfilment and billing features
ship — exactly as the audit model pre-defines `reminder_sent` / `payment_entitlement_changed`.
The payment events (9–11) **must** be emitted server-side from the Stripe webhook handler, never
from the browser, so they remain authoritative (see below). See the Maintainer TODOs in the PR.

## What we record — and what we never record

Every event records **only**:

- `event_type` — the funnel milestone;
- `plan` — `free` | `plus` | `work`;
- `group_id` — the server-side surrogate key, used purely to correlate a single exchange's funnel;
- `occurred_at` — ISO-8601 UTC timestamp;
- `idempotency_key` — deterministic dedup key (partition key of the table);
- `dimensions` — an **allow-listed** map of aggregate values.

Dimensions are constrained by an allow-list in `AnalyticsDimensions`
(`Humbugg.Api/Services/ProductAnalytics.cs`). The **only** permitted keys are:

```
participant_count  member_count  ready_count  exclusion_count
is_repeat  plan_from  plan_to  billing_cadence  days_to_draw
```

`AnalyticsDimensions.Sanitize` enforces this two ways: (1) any key not on the allow-list is
dropped, and (2) even an allow-listed key is dropped if its value trips the shared
`AuditRedaction` secret/token detector. As a result the following are **structurally impossible**
to record: **wishlist text, addresses, email addresses, invite tokens, and assignments** (giver →
recipient pairs). This is enforced by tests in `ProductAnalyticsTests` that fail if any prohibited
field survives sanitisation.

## Primary metrics

All metrics are ratios or aggregates over the events above; none require private data.

| Metric | Formula |
|---|---|
| **Create-to-draw completion** | `count(distinct group_id: draw_completed) / count(distinct group_id: group_created)` |
| **Invite-to-join** | `count(participant_joined) / count(distinct group_id: invite_sent)` |
| **Readiness** | `count(participant_ready) / count(participant_joined)` |
| **Time-to-draw** | `median(days_to_draw over draw_completed)` (also p90) |
| **Gift completion** | `count(gift_received) / count(gift_sent)` |
| **Repeat use** | `count(repeat_exchange_created) / count(distinct group_id: group_created)` |
| **Plus conversion** | `count(plan_upgraded where plan_to = plus) / count(distinct group_id: group_created where plan = free)` |
| **Work retention** | `count(subscription_renewed where plan = work) / (count(subscription_renewed where plan = work) + count(subscription_cancelled where plan = work))` |

## Server-side authority

All analytics events originate on the server, inside `GroupService` / (future) the Stripe webhook
handler — never from a client API call. There is no "track this event" endpoint. Security- and
payment-sensitive milestones (`draw_completed`, `plan_upgraded`, `subscription_*`) are therefore
authoritative: a client cannot forge, inflate, or suppress them.

## Duplicate control

Every event carries a deterministic `idempotency_key`. The DynamoDB sink
(`DynamoDbAnalyticsSink`) writes with `ConditionExpression = attribute_not_exists(idempotency_key)`
and swallows the resulting `ConditionalCheckFailedException`, so retries, double-clicks, and
at-least-once redelivery all collapse to a single counted event. Keys are scoped to the natural
unit of the transition (per group, per member, or per billing period) so a milestone is counted
once.

## Disabling analytics

Analytics is **opt-out**. Set the Lambda env var / GitHub Actions var `HUMBUGG_ANALYTICS_ENABLED`
to `false` (`0` / `off` / `no`) to disable it globally; `ProductAnalytics.TrackAsync` then
short-circuits before building or writing any event. The default (`true`, or unset) keeps analytics
on. No product behaviour depends on analytics — emission is best-effort and never throws into the
request path, so a disabled or failing sink can never break a user action.

## Minimal internal reporting path

There is **no product or public API** surface for analytics. Two internal, zero-extra-infra paths
exist for engineers with production IAM access:

1. **CloudWatch Logs Insights (fastest).** Every event is also written as a structured log line
   `analytics_event type=… plan=… group=… dimensions=…` by `ProductAnalytics`. Example:

   ```
   fields @timestamp, @message
   | filter @message like /analytics_event/
   | parse @message "type=* plan=* group=*" as event_type, plan, group_id
   | stats count_distinct(group_id) by event_type
   ```

2. **DynamoDB → S3 → Athena (durable).** The `humbugg-prod-analytics-events` table has point-in-time
   recovery enabled; export a consistent snapshot to S3 (`aws dynamodb export-table-to-point-in-time`)
   and run the metric formulas above in Athena. This is the path for funnel ratios that join events
   by `group_id`.

Access is governed by the same account IAM/SSO controls as every other production DynamoDB table.
