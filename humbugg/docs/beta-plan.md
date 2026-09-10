# Humbugg beta plan (#162)

Validates the Free/Plus boundary and the new differentiators solve real organizer problems before
broad promotion. Work is deferred (epic #638) — no Work cohort.

## Cohorts

| Cohort | Who | What it tests |
|---|---|---|
| Free groups | Representative small exchanges (family, friend groups) at or near the 6-participant limit (`HUMBUGG_FREE_PARTICIPANT_LIMIT`) | The unpaid path end to end: create → invite → wishlist → draw → gift status → repeat |
| Plus organizers | Organizers who hit the Free limit or want a Plus-only capability (managed invitations, reminders, co-organizers, customization, templates, late-participant reassignment) | Whether $12 buys something an organizer actually reaches for, and whether the six capabilities wired to a screen by #574 read as worth paying for |

No Work cohort — there is no organization/tenant model, no Work checkout, no Work screen to test
(#638).

## Success measures

Mapped to `docs/analytics.md`'s funnel events where one exists; otherwise marked not measurable
today, with what emitting it would need.

| Measure | Analytics event(s) | Status |
|---|---|---|
| Exchange creation | `group_created` (dimension `is_repeat`) | Measurable — wired |
| Invite acceptance | `invite_sent` → `participant_joined` (the "Invite-to-join" ratio in `analytics.md`) | Measurable — wired |
| Wishlist completion | `participant_ready` (the "Readiness" ratio: `participant_ready` / `participant_joined`) | Measurable — wired |
| Draw completion | `draw_completed` (dimensions `participant_count`, `days_to_draw`; the "Create-to-draw completion" and "Time-to-draw" metrics) | Measurable — wired |
| Reminders (sent, and whether they move readiness/draw completion) | none in `analytics.md`'s funnel. `reminder_sent` exists only as a security **audit** action (`humbugg/infra/README.md`), not a product-analytics event, so it cannot be joined against the funnel today | **Not measurable today** — would need a new allow-listed analytics event (e.g. `reminder_sent` with a `group_id` correlation key) emitted from `ReminderService` alongside the existing audit write |
| Purchase conversion | `plan_upgraded` (dimensions `plan_from`, `plan_to`, `billing_cadence`; the "Plus conversion" metric) | **Defined, not yet emitting** — `analytics.md`: "Events 7–11 ... are defined and ready to emit the moment ... billing features ship." Blocked on the same chain as launch: webhook re-point (#639) → `HUMBUGG_STRIPE_MODE=test` (#640) → live mode (#159) |
| Support burden | none | **Not measurable today** — Humbugg has no ticketing system integration; the nearest proxy is counting inbound `support@humbugg.com` mail by hand during the beta window |

Two metrics from `analytics.md` are useful context even though #162 doesn't name them directly:
**Repeat use** (`repeat_exchange_created` / `group_created`) and **Gift completion**
(`gift_received` / `gift_sent`, both wired).

## Consented qualitative feedback

A short questionnaire, sent once per cohort member after their exchange reaches a natural stopping
point (draw completed for Free; a Plus capability used, for Plus organizers). Four questions:

1. How much did you trust Humbugg with your group's information?
2. How easy was it to set up your exchange?
3. Was $12 for Plus worth it for what it unlocked? (Plus cohort only)
4. What would you have used instead, and why did you pick Humbugg?

**Consent sentence**, shown before the questionnaire and logged with the response:

> "Your answers help us decide what to build next. We'll never ask about your assignment, your
> gift, or anyone else in your exchange — only about your experience using Humbugg. Participation
> is optional and you can stop at any time."

### What is NOT collected

Matches the structural exclusions `docs/analytics.md` already enforces (`AnalyticsDimensions`
allow-list + `AuditRedaction` secret/token detector): **assignments** (giver → recipient pairs),
**gift contents** (wishlist text), and **private support messages**. The questionnaire is a
separate, opt-in surface from product analytics — it must not ask any question whose honest answer
would require naming a recipient, a gift, or the content of a support conversation.

## Defect tracking

Every defect or product change found during the beta is a **separate GitHub issue**, labelled
`humbugg` only — no beta-specific label, so it lands in the same backlog `docs/implementation-plan.md`
already tracks. Reference the beta in the issue body, not in a label.

## Review after beta

**$12 Plus and the plan limits are configuration, not code.** All four values can change without a
deploy of application logic:

| Value | Env var | Where it's read |
|---|---|---|
| Free participant limit | `HUMBUGG_FREE_PARTICIPANT_LIMIT` (default 6) | `PlanCatalog.cs:107` |
| Plus participant limit | `HUMBUGG_PLUS_PARTICIPANT_LIMIT` (default 50) | `PlanCatalog.cs:108` |
| Work participant limit | `HUMBUGG_WORK_PARTICIPANT_LIMIT` (default 10,000) | `PlanCatalog.cs:109` — inert while Work is hidden |
| Plus price | `HUMBUGG_PLUS_PRICE_CENTS` (default 1200) | `PlanCatalog.cs:110` |

**`HUMBUGG_PLUS_PRICE_CENTS` must move together with the actual Stripe price**
(`HUMBUGG_PLUS_PRICE_ID`, `PlanCatalog.cs:113`) — the cents figure is display and validation only;
what Stripe actually charges is whatever price object that id points at. Changing one without the
other means the app tells the organizer a number Stripe doesn't honor.

Beta feedback on question 3 (is $12 worth it) and observed drop-off at the Free participant limit
are the inputs to this review — not a decision made by this document.

## Launch-recommendation template

To be filled in after the beta window closes.

```markdown
## Humbugg beta — launch recommendation

**Window:** <start date> – <end date>
**Cohorts:** <N> Free groups, <N> Plus organizers

### Success measures observed
- Create-to-draw completion: <value>
- Invite-to-join: <value>
- Readiness: <value>
- Time-to-draw (median / p90): <value>
- Gift completion: <value>
- Repeat use: <value>
- Plus conversion: <value, or "not measured — billing not yet live in prod">

### Qualitative feedback summary
<themes from the four-question survey>

### Recommendation
<go / no-go / go-with-conditions>

### Unresolved risks
<carried over from docs/launch-checklist.md's Go/no-go section, plus anything the beta itself
surfaced that wasn't already known>
```

## Related documents

- [`implementation-plan.md`](implementation-plan.md) — what is built, what order work lands in
- [`launch-checklist.md`](launch-checklist.md) — the launch readiness checklist (#163)
- [`analytics.md`](analytics.md) — the funnel events and metrics cited above
