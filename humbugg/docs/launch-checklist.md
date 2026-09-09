# Humbugg launch checklist (#163)

Acceptance criteria from #163, turned into rows. Work items moved to epic #638
on 2026-09-09 — Work is deferred and out of scope here.

Status values: **done** · **pending PR #N** · **pending operator** · **blocked on #N**.

## 1. Domain, certs, DNS, redirects, auth callbacks

| Check | Evidence | Owner | Status |
|---|---|---|---|
| `www.humbugg.com` serves the marketing site | `smoke-test` job, `.github/workflows/humbugg-prod.yaml:849-851` (curls `/`, greps content + meta description) | repo | done |
| `robots.txt` / `sitemap.xml` present | `humbugg-prod.yaml:852-853` | repo | done |
| Apex `humbugg.com` 308s to `www`, preserving path and query | `humbugg-prod.yaml:858-860` (asserts the exact redirect target) | repo | done |
| `www` no longer forwards `/join/*` to the app (404, not a stale redirect) | `humbugg-prod.yaml:867-869` | repo | done |
| `app.humbugg.com` SPA answers a deep link, not only `/` | `humbugg-prod.yaml:872-874` | repo | done |
| `api.humbugg.com` health check + CORS preflight (unauthenticated `OPTIONS`) | `humbugg-prod.yaml:877-899` | repo | done |
| ACM wildcard cert covers apex, `www`, `app`, `api`, `auth` | `humbugg/infra/modules/certificates`, `humbugg/docs/auth-managed-login.md:89-96` (`auth.humbugg.com` added as a SAN) | repo | done |
| Cognito Managed Login callback URLs are the production ones | `humbugg/infra/envs/prod/main.tf:45` — `{app_base_url}/auth/callback` and `humbugg://auth/callback` | repo | done |
| Anonymous routes actually reachable through the gateway authorizer | `humbugg-prod.yaml:914-926` (`/api/plans` = 200, invitation/preview routes ≠ 401) | repo | done |
| A tier crosses API Gateway with an authenticated call before/after every deploy | none today — every tier stops at the dev backend or a stub (#586) | repo | blocked on #586, #642 |

## 2. Stripe: live mode, webhook, prices, receipts, refund policy

| Check | Evidence | Owner | Status |
|---|---|---|---|
| Live-mode merchant identity, verification, statement descriptor | #159 acceptance criteria — not started | operator | blocked on #159 |
| Live Plus price created via the same configurable model as test | #159 criterion; test price exists (`price_1TuugcK4tW5AWYogYC6QLwVm`, untagged — PR #647 body) | operator | blocked on #159 |
| Prod billing mode is a recorded decision, not a leftover | today: `HUMBUGG_STRIPE_MODE=disabled` in `humbugg-production`, set 2026-07-20 and never revisited (#640) | operator | pending operator (#640), then PR #647 doc |
| Webhook endpoint points at a host the request can reach | today registered at `https://humbugg.com/...` (marketing CloudFront, 403s); real route is `https://api.humbugg.com/api/billing/stripe/webhook` (#639) | operator | blocked on #639 (Stripe Dashboard edit) |
| Prod smoke proves the webhook route is reachable (not gateway-swallowed) | added in PR #647 (`humbugg-prod.yaml` smoke step, accepts 400 or 409 — see PR body) | repo | pending PR #647 |
| `docs/stripe-setup.md` names the correct webhook host | still says `https://humbugg.com/api/billing/stripe/webhook` (`humbugg/docs/stripe-setup.md:60`) | repo | pending PR #647 |
| Test-mode purchase path exercised in prod (Checkout → webhook → entitlement) | needs `HUMBUGG_STRIPE_MODE=test` (#640) + the webhook fix (#639) first, then #160's payment matrix | operator + repo | blocked on #639, #640, then #160 |
| Receipts / invoices | Stripe-hosted (Checkout email receipt + customer portal); no Humbugg-side receipt code to verify beyond passing the charge through | operator (Stripe dashboard config) | pending operator, verifiable once live |
| Refund policy published | `humbugg/marketing/src/pages/RefundPage.tsx` — full refund pre-draw, duplicate/erroneous charges always refunded, post-draw discretionary | repo | done |
| Refund actually exercised end to end | #160 criterion ("Test Plus success, cancellation, failure, ... refund, and receipt access") | operator | blocked on #160 |

## 3. SES production sending, DKIM/MAIL FROM, suppression, required email, support forwarding

| Check | Evidence | Owner | Status |
|---|---|---|---|
| SES domain identity, DKIM, MAIL FROM all `SUCCESS` before every prod deploy proceeds | `.github/workflows/humbugg-prod.yaml:267-283` ("Wait for SES domain authentication" — polls `sesv2 get-email-identity`, fails the deploy after 10 minutes if not `SUCCESS`/`SUCCESS`/`SUCCESS`) | repo | done |
| DKIM/MAIL FROM confirmed live (not only gated on deploy) | #641: "SES outbound is fully authenticated (domain, DKIM and MAIL FROM all `SUCCESS`)" — verified 2026-09-09 | repo | done |
| Google Workspace DKIM for `support@humbugg.com` replies | `google._domainkey.humbugg.com` TXT record absent (`count = 0` in `humbugg/infra/modules/email/main.tf`); SES side unaffected | operator | blocked on #641 |
| DMARC policy | `p=none; adkim=r; aspf=r; pct=100` (`humbugg/infra/modules/email/main.tf:97`) — nothing bounces today, no enforcement | repo | done at `p=none`; see "Known limitations" |
| Suppression handling (bounce/complaint → suppressed, not retried) | shared Mailer platform: SES account suppression list, `mailer/docs/operations.md:40` | repo | done, unexercised for Humbugg specifically — see #160 |
| Required email types deliver and classify correctly | `humbugg/docs/email-operations.md` (`EmailClassification`: Invitation, DrawCompleted, AssignmentAvailable always send; Reminder, AccountExchangeEvent honor the opt-out) | repo | done (code); scenario matrix pending #160 |
| Delivery/bounce/complaint feedback loop proven live | `email-feedback-smoke-test` job, `.github/workflows/humbugg-prod.yaml:761-825` — sends to SES mailbox simulator addresses, polls `humbugg-prod-email-messages` for the expected status | repo | done |
| Support forwarding (`support@humbugg.com`) | Google Workspace domain alias, no forwarding Lambda; `humbugg/docs/support-email.md` | repo | done |

## 4. Free + Plus end to end, desktop and mobile

| Check | Evidence | Owner | Status |
|---|---|---|---|
| Free milestone complete | `docs/implementation-plan.md` — 13/13 closed, #138 closed 2026-09-02 | repo | done |
| Plus milestone complete and reachable | `docs/implementation-plan.md` — 10/10 closed; #574 wired all six capabilities to a screen | repo | done |
| Stubbed browser suite (every PR) | `app/e2e/*.spec.ts` via Playwright, fixtures — `humbugg/docs/TESTING.md` | repo | done, every PR |
| Mobile widths, keyboard reach, privacy | `app/e2e/verification.spec.ts` — 320/390/414px, no wishlist/address/token in console, invite secret never leaves the fragment (`free-verification-checklist.md`) | repo | done |
| Live browser suite against a real dev backend | `E2E_LIVE=1`, `npm run e2e:live` | repo | done, local-only by design |
| A real signed-in request proves the app talks to a real pool | PR #647 — `app/e2e/session.spec.ts`, live tier: access token → `GET /api/me` 200 with matching `sub`; ID token → 401; no token → 401 | repo | pending PR #647 |
| Manual two-account walkthrough (create → share → join → wishlist → exclusions → draw → assignment → questions → gift status → repeat) | `free-verification-checklist.md` "The walkthrough" | operator | pending operator |
| Screen reader (VoiceOver/TalkBack), focus order, focus visibility, dialog trap, error/save announcements, largest text size, Reduce Motion | `free-verification-checklist.md` "Assistive technology" — needs a real device, not scriptable | operator | pending operator |
| Failure/recovery paths (broken invite link, removed-from-exchange, network loss mid-save, concurrent-edit conflict, 7th-participant limit) | `free-verification-checklist.md` "Failure and recovery" | operator | pending operator |

## 5. Accessibility

| Check | Evidence | Owner | Status |
|---|---|---|---|
| Every control has an accessible name; the `FieldLabel`/`aria-label` trap is caught | `npm run a11y:check` (`app/tool/accessibility-audit.ts`), every PR | repo | done |
| Colour contrast, WCAG AA | `app/src/theme/contrast.test.ts`, every PR | repo | done |
| Rendered-page width/keyboard/privacy checks | `app/e2e/verification.spec.ts`, every PR | repo | done |
| Real screen reader, gesture nav, largest text size, Reduce Motion | `free-verification-checklist.md` "Assistive technology" | operator | pending operator |

## 6. Security controls

| Check | Evidence | Owner | Status |
|---|---|---|---|
| Authorization invariants (owner/co-organizer/member boundaries) | `humbugg/docs/threat-model.md` §2 | repo | done |
| Invite-token leakage, enumeration, spam invitation, assignment disclosure, webhook forgery, entitlement tampering scenarios reviewed | `threat-model.md` §3 | repo | done (design); §3.7/§3.8 real-money proof waits on #160 |
| Edge rate limiting beyond the API Gateway stage throttle | none — RR2 in `threat-model.md` §7: "No edge WAF; the aggregate API Gateway throttle is the only rate control on unauthenticated floods" | repo | blocked on #183 |
| Outbound-request SSRF boundary (og:image fetch, #129) | `threat-model.md` §1 "Outbound requests (#129)", `WishUrlSafety` | repo | done |
| Audit trail for sensitive actions | `humbugg-prod-audit-events`, append-only, `deletion_protection_enabled = true` (`humbugg/infra/modules/storage/main.tf:173-198`) | repo | done |
| Breach-response procedure | PR #648, `docs/breach-response.md` (GDPR Art. 33/34: detection, severity triage, 72-hour clock, notification templates) | repo | pending PR #648 |

## 7. Backups

| Check | Evidence | Owner | Status |
|---|---|---|---|
| Point-in-time recovery, per table | `humbugg/infra/modules/storage/main.tf` — see finding below | repo | **partial — finding** |

**Finding.** Of Humbugg's 13 DynamoDB tables, 7 have `point_in_time_recovery { enabled = true }`:
`audit-events` (line 194), `analytics-events` (216), `billing` (265), `invitations` (289),
`reminders` (307), `templates` (325), `questions` (371). **6 do not**: `profiles` (71-83),
`groups` (85-97), `groupmembers` (99-133), `wishes` (139-157), `draws` (159-171),
`email-messages` (221-239, has a 90-day TTL instead, which is intentional for that table).

The tables without PITR are exactly the ones holding the exchange itself — who is in it, what they
wished for, who they were drawn for. A bad deploy or a bug that corrupts a `groups` or `draws` row
has no point-in-time restore path today. This was not raised by any open issue found in this repo;
recorded here as a launch finding, not fixed by this PR.

## 8. Monitoring, alarms

| Check | Evidence | Owner | Status |
|---|---|---|---|
| Any alarm exists and notifies someone | today: one alarm (`humbugg-prod-email-status-errors`), `alarm_actions: []`, zero SNS topics (#585, verified live 2026-09-09) | repo | blocked on #585 |
| API Lambda error/throttle alarms | PR #643 — `humbugg-prod-api-errors` (≥3/300s), `humbugg-prod-api-throttles` (≥1/300s) | repo | pending PR #643 |
| API Gateway 5xx alarm | PR #643 — `humbugg-prod-api-5xx` (≥3/300s) | repo | pending PR #643 |
| DynamoDB throttle alarms, all 13 tables | PR #643 — `humbugg-prod-<table>-{read,write}-throttles` ×13 | repo | pending PR #643 |
| The pre-existing email-status alarm actually notifies | PR #643 moves it into `modules/alerting`, adds `alarm_actions`/`ok_actions` via a `moved {}` block (history preserved) | repo | pending PR #643 |
| Mailer-side alarms (Humbugg's send/status DLQs live in mailer's stack, invisible to Humbugg's own alerting) | PR #644 — `mailer-prod-alerts` topic, DLQ-not-empty and oldest-message-age alarms | repo | pending PR #644 |
| SNS subscription actually confirmed (not `PendingConfirmation`) | operator step named in both PR bodies — `aws sns list-subscriptions-by-topic`, click the confirmation email | operator | pending operator, after #643/#644 merge |
| Alarm round-trip proven (`set-alarm-state` ALARM → OK, mail received both ways) | operator step named in both PR bodies | operator | pending operator |
| `HUMBUGG_ALERT_EMAIL` / `MAILER_ALERT_EMAIL` secrets created | named as still-needed in both PR bodies | operator | pending operator |

## 9. Dashboards

None exist. No `aws_cloudwatch_dashboard` resource anywhere under `humbugg/infra/`. Operational
visibility today is CloudWatch Logs Insights queries (e.g. `docs/analytics.md` "Minimal internal
reporting path") and the alarms above once PR #643/#644 land — not a dashboard. Not blocking launch;
listed as a known limitation below.

## 10. Pricing / terms / privacy / refund / support published

| Check | Evidence | Owner | Status |
|---|---|---|---|
| Pricing page, prices sourced from `GET /api/plans` (never hardcoded) | `humbugg/marketing/src/pages/PricingPage.tsx` | repo | done |
| Terms | `humbugg/marketing/src/pages/TermsPage.tsx` | repo | done |
| Privacy policy | `humbugg/marketing/src/pages/PrivacyPage.tsx`; PR #645 adds §8 storage disclosure (Cognito tokens, PKCE/CSRF state, `humbugg.plus.intent`) and a restriction/objection paragraph | repo | pending PR #645 for the storage disclosure; base policy already live |
| Refund policy | `humbugg/marketing/src/pages/RefundPage.tsx` | repo | done |
| Support contact | `support@humbugg.com`, `docs/support-email.md` | repo | done |
| Sub-processor disclosure | PR #645 — new `/sub-processors` route (AWS, Stripe, Google Workspace; transfer mechanism per processor) | repo | pending PR #645 |
| DPA acceptance actually recorded (not just the page published) | PR #645's `gdpr-compliance.md` §7 operator checklist — AWS/Stripe/Google DPA acceptance dates, all unticked | operator | pending operator (#190 stays open for this) |
| Policy version bump for the Work-hiding content change | PR #646 bumps `POLICY_VERSION` `2026.1` → `2026.2`, effective 2026-09-10, in both marketing and app `policies.ts` | repo | pending PR #646 |

## 11. Deployment / rollback ownership

| Check | Evidence | Owner | Status |
|---|---|---|---|
| Runbook: deploy, rollback, alarm/escalation table | PR #648, `docs/runbooks.md` §7 | repo | pending PR #648 |
| The dropped-deploy trap when merging several PRs to `main` in quick succession | `docs/implementation-plan.md` "Traps that have already cost time" — `cancel-in-progress: false` queues but GitHub keeps only one pending run per group, so a third merge cancels the second's queued run; happened 2026-08-27 | repo | documented; operator must apply it merging this launch stack (see the addition to `implementation-plan.md`) |
| A tier crosses API Gateway so a lost route is caught before prod, not after | none today (#586) | repo | blocked on #586 |
| Prod smoke account for an authenticated post-deploy check | #642 — reserved `.test` Cognito user, `smoke-session.mjs`, asserts `/api/me` 200 / ID token 401 | repo + operator (account creation) | blocked on #642 |

## 12. Launch record

This file plus `docs/launch-evidence.md` (landing separately, #160) together are the launch record:
approvals, known limitations, and follow-up issues. `docs/beta-plan.md` (this PR, #162) is the
pre-launch validation step; its "review after beta" section feeds the go/no-go below.

---

## Known limitations at launch

- **Work is deferred.** No org/tenant model, no Work checkout, no Work screen — epic #638.
- **No CloudWatch dashboards.** Logs Insights queries and alarms (once #643/#644 land) are the only
  operational visibility.
- **DMARC is `p=none`.** Nothing enforces SPF/DKIM alignment; #183's WAF work and any DMARC
  tightening both wait on deliverability monitoring (`humbugg/infra/README.md`).
- **Google Workspace DKIM for `support@humbugg.com` is not configured** — replies from support carry
  no DKIM signature (#641). SES outbound (the product's own mail) is unaffected.
- **6 of 13 DynamoDB tables have no point-in-time recovery** — `profiles`, `groups`, `groupmembers`,
  `wishes`, `draws` (`email-messages` is TTL'd by design). See the Backups finding above.
- **No edge WAF.** The API Gateway stage throttle is the only defense against unauthenticated floods
  (`threat-model.md` RR2, #183).
- **No test tier crosses API Gateway before merge.** Every tier below prod smoke stops at a fake, a
  stub, or the dev backend directly — a lost gateway route (as #582 was) is caught only after deploy
  (#586).
- **Stripe is test-mode only.** No live payments can be taken until #159's go/no-go.

## Go/no-go

**No-go today.** Blocking items, in the order they have to land:

1. **#639** — repoint the Stripe webhook at `api.humbugg.com` (operator, Stripe Dashboard).
2. **#640** — set `HUMBUGG_STRIPE_MODE=test` in prod, after #639 (operator, GitHub environment var).
3. **PR #647** — merge (adds the webhook reachability smoke assertion and the authenticated
   session e2e spec).
4. **#585 / PR #643, #644** — merge and confirm the SNS subscriptions before anything else ships,
   so the rest of this launch is observable.
5. **#160** — run the full payment/email matrix once #639/#640 are live in test mode.
6. **#159** — merchant identity and live-mode go/no-go. Last, by design: nothing upstream can be
   honestly tested against real money before this.
7. **PR #645, #646, #648** — legal/disclosure content and runbooks; no code dependency on the above,
   land whenever ready.
8. **Operator-only rows** throughout this checklist (manual walkthrough, assistive technology,
   DPA acceptance dates, SNS confirmation, Google DKIM) — none blocks the others, all block launch.

The PITR gap (Backups, above) is a finding, not yet an issue — worth opening before launch rather
than after a bad write.

## Related documents

- [`implementation-plan.md`](implementation-plan.md) — what is built, what order work has to land in
- [`beta-plan.md`](beta-plan.md) — pre-launch validation (#162)
- [`free-verification-checklist.md`](free-verification-checklist.md) — the manual half of #138
- [`threat-model.md`](threat-model.md), [`analytics.md`](analytics.md), [`stripe-setup.md`](stripe-setup.md), [`support-email.md`](support-email.md), [`email-operations.md`](email-operations.md)
- `docs/launch-evidence.md` — landing separately (#160)
