# Humbugg operating runbooks

For one person operating Humbugg. Free and Plus only — Work is deliberately unbuilt (#638);
none of this covers Work tenancy.

Every section: trigger → what to check → what to do → what to record. "Record" means one of:
an audit-trail query (evidence already exists, nothing to write), a new GitHub issue, or an
entry in the private incident log (see [`breach-response.md`](breach-response.md) for where
that lives — it is not this repo).

Read first: [`../CLAUDE.md`](../CLAUDE.md) (AWS profile, GitHub access), `threat-model.md`
§8 (security operational response, overlaps with §7 below), `stripe-setup.md`,
`email-operations.md`, `support-email.md`, `data-retention-deletion.md`, `gdpr-compliance.md`.

Keep out of this file and everything you write while following it: personal inbox addresses,
credentials, webhook URLs, AWS account ids. A pattern match for those shapes over this file
should return nothing.

---

## 1. Billing

Plus is a one-time $12 purchase via Stripe Checkout (test mode today — `docs/stripe-setup.md`
§7, live mode blocked on #159). The webhook (`POST /api/billing/stripe/webhook`, routed on
`api.humbugg.com` — not the apex, see the note under "paid but no Plus") writes the
entitlement. There is no subscription or renewal — none of this section applies to recurring
billing because Humbugg has none yet.

The ledger is `humbugg-prod-billing`, one table, `record_id` partition key:
`payment#{purchaseId}` (the purchase), `event#{stripeEventId}` (idempotency marker),
`active#{groupId}` (which purchase is in flight for a group, deleted on refund/fail/expiry).
Look up everything for one group with the `group_id-index` GSI:

```bash
aws dynamodb query \
  --table-name humbugg-prod-billing \
  --index-name group_id-index \
  --key-condition-expression "group_id = :g" \
  --expression-attribute-values '{":g":{"S":"<group-id>"}}'
```

`status` on the `payment#` record is one of `pending`, `paid`, `failed`, `expired`,
`refunded`. That, not the Stripe dashboard, is what the app itself believes.

### Refund request

1. **Check**: find the group's `payment#` record (above); confirm `status = paid`.
2. **Do**: process the refund in the Stripe Dashboard (test mode — Payments → the charge →
   Refund). This emits `charge.refunded`, which the webhook consumes and (if the caller is
   still the group's owner and still holds the `plus:{groupId}` entitlement) flips the group's
   `plan` back to `free` and removes `entitlement_id` — see `BillingRepository.ApplyEventAsync`.
3. **Verify**: re-run the query above; `status` should read `refunded` within a minute of the
   webhook firing. If it does not move, check the webhook endpoint's delivery log in the
   Stripe Dashboard (Developers → Webhooks → the endpoint → recent deliveries) for a failed
   delivery, and check the `humbugg-prod-api-5xx` / `humbugg-prod-api-errors` alarms (§7).
4. **Record**: nothing to write — the status transition is the record. If the group had
   already been deleted or its owner changed before the refund, the entitlement mutation is
   skipped by design (the transaction requires `owner_user_id` and `entitlement_id` to still
   match) and only the payment/event rows update; note that in a reply to the customer rather
   than in this repo.

### Duplicate charge

The app itself cannot produce one for the same group: `ReserveAsync` writes an `active#{groupId}`
marker with `attribute_not_exists`, so a second Checkout cannot be reserved while one is
pending or paid for that group. A duplicate charge is therefore either (a) the customer paid
for two different groups (not a duplicate — verify by `group_id` on each `payment#` record),
or (b) a genuine Stripe-side double-submit on the same Checkout Session.

1. **Check**: query the group(s) above; compare `checkout_session_id` / `payment_intent_id`
   across the `payment#` records against the charges in the Stripe Dashboard.
2. **Do**: refund the extra charge in the Stripe Dashboard (same as above). Humbugg's own
   entitlement state is driven by the group's own `payment#` record, so refunding a second,
   unrelated Stripe charge does not touch it — only a `charge.refunded` for the charge tied to
   that group's `payment_intent_id` does.
3. **Record**: nothing in-repo; the Stripe Dashboard refund is the record.

### Dispute / chargeback

1. **Check**: Stripe Dashboard → Payments → Disputes. Note the charge, group, and reason.
2. **Do**: respond to the dispute in Stripe with the evidence Stripe requests (this is a
   Stripe-side workflow, not a Humbugg one). Stripe does not emit a webhook event Humbugg
   subscribes to for disputes (see the subscribed list in `stripe-setup.md` §2), so **the
   entitlement does not change automatically** — decide manually whether to revoke Plus for
   the group while the dispute is open (there is no API for a partial/temporary revoke; the
   only lever is the same refund path above, which the customer keeping the dispute open may
   not want).
3. **Record**: log the dispute outcome for your own reference; nothing in-repo.

### "Paid but no Plus"

The distinction: **paid** is a Stripe fact (`payment#` status = `paid`); **Plus** is an
entitlement fact (the group's `entitlement_id = plus:{groupId}`, checked by
`PlanCatalog.HasCapability`). A customer can be paid without the entitlement if the webhook
never reached the app, or reached it but the transaction condition failed (group deleted,
ownership changed, or an unrelated entitlement already present).

1. **Check**:
   - The `payment#` record's `status` (above). If it is not `paid`, the customer has not
     actually completed Checkout yet — direct them back to the billing area, which polls for
     the entitlement, not for `status: paid` (`stripe-setup.md` §4).
   - If `status = paid` but the group's `plan` is still `free` (`aws dynamodb get-item
     --table-name humbugg-prod-groups --key '{"group_id":{"S":"<group-id>"}}'`), the webhook
     either never arrived or its transaction condition failed.
   - The webhook endpoint's delivery log in the Stripe Dashboard (Developers → Webhooks → the
     endpoint) shows every attempt and its response code. A `4xx`/`5xx` there means the
     application rejected or never saw the event.
2. **Known trap (#639)**: `stripe-setup.md` historically pointed the Dashboard endpoint
   registration at `https://humbugg.com/api/billing/stripe/webhook` — the apex, which is the
   *marketing* CloudFront distribution and answers `403`. The route only exists on
   `https://api.humbugg.com/api/billing/stripe/webhook` (`infra/modules/compute/main.tf`, the
   `stripe_webhook` route). If the delivery log shows `403` on every attempt, the endpoint URL
   registered in the Stripe Dashboard is the apex, not `api.humbugg.com` — fix the endpoint URL
   in the Dashboard; no redeploy needed.
3. **Do**: once the cause is fixed (webhook URL, or a transient app error), replay the event
   from the Stripe Dashboard delivery log ("Resend"). Re-check the group's `plan`/`entitlement_id`
   after the replay.
4. **Record**: nothing in-repo for an isolated case. If the apex-URL trap is what you found,
   confirm the Dashboard endpoint URL is fixed and mention it in your reply so it doesn't
   recur for the next purchase.

### Receipt request

Stripe hosts the receipt. Point the customer at the Stripe-hosted receipt link from their
Checkout confirmation, or issue one from the Stripe Dashboard (Payments → the charge → the
"..." menu → Resend receipt / Refund receipt has its own link). Humbugg does not generate or
store receipts.

---

## 2. Email

Humbugg submits product email through the shared Mailer platform, which owns SES sending,
suppression, and both DLQs Humbugg's own traffic can land in
([`email-operations.md`](email-operations.md); platform-level recovery is
`mailer/docs/operations.md`).

### SES sending-pause / reputation alarms

`mailer-prod-ses-bounce-rate` (`AWS/SES` `Reputation.BounceRate`, 900s avg, alarms above
`0.05`) and `mailer-prod-ses-complaint-rate` (`Reputation.ComplaintRate`, 900s avg, above
`0.001`) are account-wide — SES reputation is shared across every application sending from
this AWS account, not scoped to Humbugg.

1. **Check**: which category is driving it. `humbugg-prod-email-messages` records delivery
   state per message (no address, per `email-operations.md`); cross-reference recent
   `bounce`/`complaint` records there against send volume by category
   (`Invitation`/`DrawCompleted`/`AssignmentAvailable`/`Reminder`/`AccountExchangeEvent`).
2. **Do**: if a specific category is misbehaving (e.g. a bad list import driving invitations
   to dead addresses), stop Humbugg's product sends without touching authentication mail:
   ```text
   /mailer/prod/humbugg/exchange-email-enabled = false
   ```
   (`aws ssm put-parameter --name /mailer/prod/humbugg/exchange-email-enabled --value false
   --overwrite`). This does not affect Cognito sign-up/recovery mail, which uses a separate
   configuration set. If the reputation issue is account-wide and not Humbugg-specific,
   escalate per `mailer/docs/operations.md` — other applications share this SES account.
3. **Record**: a GitHub issue in this repo noting the pause, cause, and when sending resumed.

### Elevated bounce/complaint (below alarm threshold)

Same check as above, at smaller scale. If a single organizer's invite list is bouncing (e.g.
they imported stale addresses), there is no per-invite email in Humbugg today — organizers
share a copy-link, not a mailer send (`threat-model.md` §3.3) — so elevated bounces almost
always trace to `Reminder` or `AccountExchangeEvent` sends to accounts whose Cognito email
went stale. No action needed below the alarm threshold beyond noting the pattern; act if it
trends toward the alarm.

### Suppression list handling

Mailer owns the suppression list (hard bounces and complaints, stored as irreversible
recipient hashes, and mirrored in the SES account suppression list —
`mailer/docs/operations.md` "Suppression removal"). Humbugg has no suppression UI or API of
its own. Removing a suppression entry requires the address owner's explicit request and
review of both the Mailer table and the SES account list; do not remove one on a hunch.
Opted-out or suppressed accounts still see the same activity in-app — the in-app fallback
means a suppressed address never means missing an exchange (`email-operations.md`).

### Domain-authentication failure

`humbugg-prod.yaml`'s `deploy-infra` job waits for the `humbugg.com` SES identity, DKIM, and
MAIL FROM (`mail.humbugg.com`) to reach `SUCCESS` before proceeding — a stuck deploy at that
gate is the first signal.

1. **Check**:
   ```bash
   dig +short TXT _amazonses.humbugg.com          # identity verification
   dig +short CNAME <token>._domainkey.humbugg.com # three DKIM CNAMEs, from the SES console
   dig +short MX mail.humbugg.com                  # MAIL FROM
   dig +short TXT mail.humbugg.com                 # MAIL FROM SPF
   ```
   Compare against Terraform state (`humbugg/infra/modules/email`) and the SES console
   (Identities → `humbugg.com`).
2. **Do**: DNS is Terraform-managed (`infra/modules/email`); a drifted or missing record is
   fixed by re-running `deploy-infra` (`workflow_dispatch`, `run_infra=true`, `run_app=false`)
   after confirming the zone (`humbugg.com`, Route53) has not been changed outside Terraform.
   If the records are correct but SES still reports `PENDING`, propagation can take up to 72
   hours — re-run the deploy once it should have landed rather than repeatedly.
3. **Record**: nothing unless it recurs; if it does, open an issue — DNS should not drift
   under Terraform ownership.

### The Humbugg DLQs

Two SQS dead-letter queues live in the Mailer stack (not Humbugg's own —
`email-operations.md`): `mailer-prod-humbugg-send-dlq` (fed by `mailer-prod-humbugg-send`,
`maxReceiveCount = 5`) and `mailer-prod-humbugg-status-dlq` (fed by
`mailer-prod-humbugg-status`, same retry count). Alarms: `mailer-prod-send-dlq-not-empty` and
`mailer-prod-status-dlq-not-empty` (`AWS/SQS` `ApproximateNumberOfMessagesVisible` max, 300s,
fires above `0`), plus `mailer-prod-humbugg-send-oldest-message`
(`ApproximateAgeOfOldestMessage` max, 300s, fires above `900s`).

1. **Check**: inspect message count and age, not body — DLQ bodies can carry personal content
   and must not be pasted into an issue (`mailer/docs/operations.md`).
   ```bash
   aws sqs get-queue-attributes \
     --queue-url "$(aws sqs get-queue-url --queue-name mailer-prod-humbugg-send-dlq --query QueueUrl --output text)" \
     --attribute-names ApproximateNumberOfMessages
   ```
   Same for `mailer-prod-humbugg-status-dlq`. Correlate with `humbugg-prod-email-status-errors`
   (send-side failures surface as stuck deliveries; status-side failures surface as this
   alarm — `email-operations.md`).
2. **Do**: find and fix the underlying cause first (a permission, validation, or SES-side
   failure) — redriving before fixing the cause just refills the DLQ. Then redrive:
   ```bash
   aws sqs start-message-move-task \
     --source-arn arn:aws:sqs:us-east-1:<account-id>:mailer-prod-humbugg-send-dlq
   ```
   (omit `--destination-arn` to redrive back to the queue's own configured source, per the
   queue's `redrive_allow_policy`; same command with `-status-dlq` for the status queue).
   Confirm queue age and the related Lambda-error alarms return to zero after redrive.
3. **Record**: a GitHub issue if the cause was a code or permission bug; nothing if it was a
   transient provider failure that resolved itself before you redrove.

---

## 3. Support inbox

`support@humbugg.com` is a Google Workspace **alias** on the Workspace owner's account, not a
separate mailbox — see [`support-email.md`](support-email.md). There is no forwarding Lambda;
inbound mail is handled entirely by Google's MX.

1. **Check** when mail stops arriving:
   ```bash
   dig +short MX humbugg.com        # expect: 1 smtp.google.com.
   dig +short TXT humbugg.com       # SPF (+ site-verification strings)
   ```
   Then, in the Google Workspace Admin console: confirm `support@humbugg.com` is still listed
   as an alias on the owner's user (Admin console → Directory → Users → the owner → user
   information → alternate emails), and that the account itself is not suspended.
2. **Fallback**: mail addressed to `support@humbugg.com` always lands in the Workspace owner's
   **primary inbox** — it is an alias, not a separate destination — so the fallback for "is
   support mail arriving at all" is simply checking that primary inbox directly rather than
   filtering for the alias.
3. **Do**: if MX or SPF has drifted from `support-email.md`'s table, it is Terraform-managed
   (`humbugg/infra/modules/email`) — re-run `deploy-infra`. If the alias itself was removed in
   the Admin console, re-add it there (not a Terraform-managed resource).
4. **Record**: nothing unless the cause recurs.

---

## 4. Deletion requests

Full policy: [`data-retention-deletion.md`](data-retention-deletion.md). This section is the
operator's checklist when someone asks by email rather than clicking the button themselves.

### Account deletion

Self-service: `DELETE /api/me` from Settings, no operator action needed. If someone asks you
to do it for them (can't sign in, etc.), you cannot run this on their behalf without their
Cognito identity — direct them to regain access (password reset) and self-serve; Humbugg has
no admin "delete this account" tool by design (no organizer/admin override exists — see
`data-retention-deletion.md` §"User — request account deletion"). What it does: profile and
product-profile content deleted; memberships in open groups deleted; memberships in drawn
groups anonymized (pseudonym `deleted-user-<sha256 prefix>`) so the draw stays valid for
everyone else; groups they organize deleted in full; audit trail retained with only the
`actor_user_id` anonymized. Idempotent — safe to ask them to retry if unsure it worked.

### Exchange (group) deletion

Only the organizer can do this (`DELETE /api/groups/{groupId}`, self-service). If the
organizer is unreachable and members want the group gone, there is no operator override — the
design deliberately gives no admin the power to delete another user's group. Advise members to
use the self-service private-data clear (below) instead.

### A member's own data within one exchange

Self-service: `DELETE /api/groups/{groupId}/members/me/private-data` clears wishlist,
avoidances, address, purchase claims, gift progress and question threads for that exchange,
without leaving the group. Idempotent.

### Billing data

Stripe retains payment/customer records under its own legal-retention policy; Humbugg cannot
delete a Stripe financial record and should not promise to. What Humbugg *can* do: account
deletion anonymizes the link between the person and any audit trail reference to their
billing activity (via `actor_user_id` anonymization) — it does not erase the Stripe record
itself, and Humbugg does not persist a first-party billing ledger of financial (as opposed to
entitlement) data. Tell the requester their payment records are retained by Stripe under
Stripe's own policy and are not part of what account/exchange deletion erases.

### Manual DSAR intake

For a rectification/restriction/objection request that has no self-service button
(`gdpr-compliance.md` §3, tracked under #192): intake at `support@humbugg.com`. Verify the
requester controls the account (they can demonstrate sign-in, or the request comes from the
verified address Cognito holds for them) before acting. Log what was requested and what was
done — there is no ticketing system in this repo; keep the email thread as the record, and
open a GitHub issue only if the request exposes a gap this repo should close (e.g. a right
with no self-service path yet).

---

## 5. Assignment emergency

The existing path is the audited emergency reveal:
`POST /api/groups/{groupId}/assignment/reveal`, organizer-only, requires a non-empty `reason`
(≤ 500 chars), and writes to `humbugg-prod-audit-events` (`event_type = "assignment_reveal"`)
**before** returning the full giver→recipient mapping (`threat-model.md` §6).

**This is the only path an assignment may be disclosed through.** If an organizer or member
asks you (the operator) to tell them who has whom — over email, chat, or a support ticket —
**do not**. Reading `humbugg-prod-draws` directly and relaying an assignment over chat
bypasses the one control that makes a reveal accountable: the audit write, the reason, and the
organizer's own action. Direct them to the in-app reveal instead.

If the organizer genuinely cannot perform the reveal themselves (account access issue) and the
situation is urgent enough to justify it, get **explicit, written confirmation** from the
organizer first — not a phone call, not a DM you paraphrase — stating (a) that they are the
group's organizer, (b) that they are requesting the full mapping be disclosed, and (c) why.
Keep that confirmation. Then have them regain account access and perform the reveal
themselves; there is no operator-side reveal tool, by design (`threat-model.md` §2.2, O1).

**Check afterward**:

```bash
aws dynamodb query \
  --table-name humbugg-prod-audit-events \
  --key-condition-expression "group_id = :g" \
  --filter-expression "event_type = :t" \
  --expression-attribute-values '{":g":{"S":"<group-id>"},":t":{"S":"assignment_reveal"}}'
```

confirms the reveal was recorded with an actor, timestamp, and reason. **Record**: the query
result above is the record; if the request came in over an out-of-band channel, keep that
written confirmation alongside it.

---

## 6. Credential rotation

| Credential | Procedure |
|---|---|
| Stripe secret key / webhook secret | [`stripe-setup.md`](stripe-setup.md) §5 — roll in the Stripe Dashboard, update the GitHub environment secret, redeploy with `run_infra=true` so Terraform rewrites the SSM `SecureString` and `update-lambda` refreshes the Lambda env. |
| Stripe publishable key | Same §5 — not secret, rarely rotated; update the GitHub var and redeploy if it changes. |
| AWS — CI | Nothing to rotate. CI assumes a role over OIDC (`aws-actions/configure-aws-credentials@v4`) and holds no long-lived key at all (root `CLAUDE.md` "GitHub access", and "Deployment (CI/CD)"). |
| AWS — the operator's own IAM access key | `aws iam create-access-key` for a new key, switch your local/environment credentials to it, confirm `aws sts get-caller-identity`, then `aws iam delete-access-key --access-key-id <old-id>` on the old one (root `CLAUDE.md` "Environment access"). The key is long-lived by design — rotate on a schedule and immediately on any suspected exposure. |
| Cognito app client | Nothing to rotate — the app client is secretless by design (`humbugg/CLAUDE.md` "Stack" table); there is no client secret to leak or roll. |

---

## 7. Health, alerts, escalation, rollback

### Alarms

All alarms publish to `humbugg-prod-alerts` (Humbugg) and `mailer-prod-alerts` (Mailer) by
email; both set `alarm_actions` and `ok_actions`, so a quiet inbox means healthy, not
unmonitored, and a recovery mail closes the loop (`humbugg/infra/modules/alerting/README.md`,
`mailer/docs/operations.md`).

**Confirm the subscription** after any infra change that could have recreated it — an SNS
email subscription delivers nothing until the recipient clicks AWS's confirmation link, and
Terraform reports it created either way:

```bash
aws sns list-subscriptions-by-topic \
  --topic-arn "$(aws ssm get-parameter --name /humbugg/prod/alerts-topic-arn --query Parameter.Value --output text)" \
  --query 'Subscriptions[].[Protocol,Endpoint,SubscriptionArn]' --output table
```

A `SubscriptionArn` of `PendingConfirmation` means nobody is being told anything; the link
expires after three days, so re-run the deploy to re-send it.

| Alarm | What it means | First check |
|---|---|---|
| `humbugg-prod-api-errors` (Lambda `Errors` ≥ 3 / 300s) | The API request path is broken — not a lone cold-start error, which resolves itself. | CloudWatch Logs for the API Lambda around the alarm window; recent deploys. |
| `humbugg-prod-api-throttles` (Lambda `Throttles` ≥ 1 / 300s) | The API Lambda was asked to run and could not — a request was dropped, no benign case. | Lambda reserved/provisioned concurrency; a traffic spike or a runaway caller. |
| `humbugg-prod-reminders-errors` (Lambda `Errors` ≥ 3 / 300s) | Scheduled reminders stopped going out. | CloudWatch Logs for the reminders Lambda; whether the schedule itself fired. |
| `humbugg-prod-marketing-errors` (Lambda `Errors` ≥ 3 / 300s) | The marketing SSR renderer is failing. | CloudWatch Logs for the marketing Lambda; recent marketing deploys. |
| `humbugg-prod-email-status-errors` (Lambda `Errors` ≥ 1 / 300s) | A delivery-status event never reached `humbugg-prod-email-messages`. Threshold is 1 — this consumer's traffic is too low for one error to be noise. | CloudWatch Logs for the email-status Lambda; the Mailer status queue and its DLQ (§2). |
| `humbugg-prod-api-5xx` (API Gateway `5xx` ≥ 3 / 300s) | A gateway-side fault the Lambda error metric never sees — an integration timeout, an authorizer failure. | API Gateway execution logs; whether it correlates with `humbugg-prod-api-errors`. |
| `humbugg-prod-marketing-5xx` (API Gateway `5xx` ≥ 3 / 300s) | Same, for the marketing SSR API. | Same, for the marketing Lambda. |
| `humbugg-prod-<table>-read-throttles` / `-write-throttles` (DynamoDB throttle events ≥ 1 / 300s) | A hot partition throttled — on-demand caps throughput per partition, not per table. | Which table; whether one key (e.g. one very active group) is the hot partition. |
| `mailer-prod-{ingress,sender,feedback}-errors` (Lambda `Errors` > 0 / 300s) | A Mailer-pipeline stage is failing — affects every application sending through Mailer, not just Humbugg. | `mailer/docs/operations.md`; correlate with Humbugg's own send/status alarms. |
| `mailer-prod-{send,feedback,status}-dlq-not-empty` (SQS visible messages > 0 / 300s) | Messages exhausted their retries. §2 covers Humbugg's two (send, status). | §2 "The Humbugg DLQs". |
| `mailer-prod-humbugg-send-oldest-message` (`ApproximateAgeOfOldestMessage` > 900s / 300s) | A Humbugg send has been stuck for 15+ minutes — the recipient has not been notified. | Same queue as the DLQ alarm above; check before it deadletters. |
| `mailer-prod-ses-bounce-rate` (`Reputation.BounceRate` > 0.05, 900s avg) | Account-wide SES reputation risk — a sustained breach can pause sending for every application on this account. | §2 "SES sending-pause / reputation alarms". |
| `mailer-prod-ses-complaint-rate` (`Reputation.ComplaintRate` > 0.001, 900s avg) | Same, complaint-driven — the tighter threshold reflects how much more damaging complaints are to sender reputation. | Same. |

Drive an alarm by hand to prove delivery without waiting for a real fault, then put it back:

```bash
aws cloudwatch set-alarm-state --alarm-name humbugg-prod-api-errors --state-value ALARM --state-reason test
aws cloudwatch set-alarm-state --alarm-name humbugg-prod-api-errors --state-value OK --state-reason test
```

### Health checks

The prod smoke job (`smoke-test` in `.github/workflows/humbugg-prod.yaml`, runs after every
deploy) is the detector, not a gate (`humbugg/CLAUDE.md` "Testing" table — it runs after
`update-lambda`/`deploy-frontend-assets`/`deploy-app`, so it always checks live surfaces even
when a path-filtered change skipped rebuilding one of them). Its URLs, runnable by hand:

```bash
curl --fail https://www.humbugg.com/                 # marketing (canonical origin)
curl --fail https://app.humbugg.com/                 # product app shell
curl --fail https://api.humbugg.com/health            # API
curl -o /dev/null -w '%{http_code}\n' https://api.humbugg.com/api/groups   # expect 401 (authorizer reachable)
curl -o /dev/null -w '%{http_code}\n' https://api.humbugg.com/api/plans    # expect 200 (AllowAnonymous route reachable)
```

A `401` on `/api/groups` without a token is healthy — it proves the request reached the
Cognito authorizer. A `403`/`404`/anything-but-`401`/`404` there, or a non-`200` on `/health`,
is the incident.

### Escalation

If an alarm re-enters `ALARM` twice within an hour without an identified transient cause
(a known deploy blip, a one-off cold start), treat it as an incident rather than noise:
check the prod smoke job's last run, then decide whether to roll back (below). API errors or
5xx alarming twice in an hour with no fix in flight is the clearest case for a rollback rather
than continued live debugging.

### Rollback

Re-run `humbugg-prod.yaml` via `workflow_dispatch` **against the last good commit** — GitHub
Actions `workflow_dispatch` runs the workflow file as it exists on the ref you pick, so
dispatching from the last-good commit (or its branch/tag) redeploys that state, not `main`'s
latest. Set `run_infra`/`run_app` based on what regressed:

- App-only regression (bad backend/frontend code, infra unaffected): `run_infra=false,
  run_app=true` — redeploys the backend/marketing/app Lambdas and assets from the chosen
  commit's build, using whatever is already in SSM.
- Infra regression: `run_infra=true, run_app=false` (or both `true` if app code also needs to
  roll back with it).

**Before dispatching, read the "Merging several PRs" trap in `implementation-plan.md`**: the
`humbugg-prod` concurrency group queues rather than cancels, but GitHub keeps only one pending
run per group, so a rollback dispatched while another run is queued can itself be dropped.
Let any in-flight run finish first, or dispatch and then confirm it actually ran (check the
Actions tab) rather than assuming it queued cleanly.

**Manual fallback** (infra untouched, just need the Lambda code back on the last-good image —
faster than a full workflow run when the image already exists in ECR):

```bash
aws lambda update-function-code \
  --function-name <humbugg-prod-api-lambda-name> \
  --image-uri <ecr-repo-url>:<last-good-sha> \
  --region us-east-1
aws lambda wait function-updated --function-name <humbugg-prod-api-lambda-name> --region us-east-1
```

Get `<humbugg-prod-api-lambda-name>` and `<ecr-repo-url>` from
`/humbugg/prod/lambda-name` and `/humbugg/prod/ecr-url` in SSM. This is a stopgap — it does
not update SSM env vars or Terraform state, so follow up with a proper `workflow_dispatch`
rollback once the immediate fire is out, or the next normal deploy will overwrite it anyway.
