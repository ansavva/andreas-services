# Humbugg Threat Model — invitations, assignments, payments, and Work tenancy

Status: living document. Owner: Humbugg maintainers. Last substantive review: this PR (#125).

This document identifies the highest-risk abuse and privacy failures for Humbugg **before** the
service is expanded with co-organizers, reminders, member questions, paid plans, and Work
(organization) tenancy. It defines the authorization invariants and rate limits every future feature
must respect, records concrete mitigations and the security tests that guard them, and lists the
residual risks with an operational response.

Two rules bound everything below:

1. **Security controls apply regardless of plan.** Free, Plus, and Work are billing tiers. They may
   change *quotas* (participant counts), never *security*. Authorization checks, rate limits,
   auditing, and secret handling are identical on every plan. A limit or check that can be bypassed
   by changing `plan` is a bug.
2. **Secrets never travel where referrers or logs can capture them.** Invite secrets live in the URL
   *fragment* and in request *bodies* — never in a path, query string, or log line.

Legend: **[NOW]** = control exists in code today and is tested. **[FUTURE]** = feature not yet built;
this document specifies the invariant/limit that the feature must ship with.

---

## 1. Assets and trust boundaries

| Asset | Sensitivity | Where it lives |
|---|---|---|
| Invite secret (32 random bytes, base64url) | High — grants group join | Returned once to organizer; only its SHA-256 hash is stored (`humbugg-<env>-groups.invite_hash`) |
| Assignment (giver → recipient map) | High — spoils the exchange | `humbugg-<env>-draws`, server-side only |
| Wishlist / avoidances / mailing address | High — personal data | `humbugg-<env>-groupmembers`, private to the member |
| Emergency-reveal audit events | High — accountability record | `humbugg-<env>-audit-events`, append-only |
| Cognito identity / access token | High — authentication | Cognito; access token validated per request |
| Plan / entitlement | Medium — controls quota | `humbugg-<env>-groups.plan` / `entitlement_id` |
| Organization / Work membership **[FUTURE]** | High — cross-tenant boundary | not yet modelled |

Trust boundaries: the **browser** (untrusted), **API Gateway HTTP API** + Cognito JWT authorizer
(authentication edge), the **ASP.NET Core Lambda** (authorization + business rules — the security
kernel), **DynamoDB** (IAM-scoped storage), and the **Mailer platform** (SigV4-signed, separate
Lambda for delivery status). Everything the browser sends is attacker-controlled; every trust
decision is made in the Lambda.

---

## 2. Authorization invariants

These are invariants: they must hold after every change. Today they are enforced centrally in
`GroupService` via `RequireMembershipAsync` / `RequireOrganizer` / `RequireOpen`
(`humbugg/backend/Humbugg.Api/Services/GroupService.cs`) and by the resource-scoped private/public
projections (`Private`, `Public`, `Assignment`, `Detail`).

### 2.1 Authenticated user (any member)
- **U1** Every `/api/**` route requires a valid Cognito **access** token whose `token_use=access`
  and `client_id` matches Humbugg's app client. Enforced in `Program.cs` (`OnTokenValidated`) and at
  the API Gateway JWT authorizer. **[NOW]**
- **U2** A user may read a group only if they hold a membership in it (`RequireMembershipAsync`
  throws `403` otherwise). Non-members cannot read group metadata, rosters, exclusions, or
  assignments. **[NOW]**
- **U3** A user may read/write only **their own** private membership data (wishlist, avoidances,
  address) via `/members/me`. There is no route that returns another member's private fields to an
  ordinary member — `Detail` projects other members through `Public`, which omits them. **[NOW]**
- **U4** A user sees only **their own** assignment (`GetAssignmentAsync`), never the full mapping.
  The full mapping is disclosed only through the audited emergency reveal (§6). **[NOW]**
- **U5** Identity comes only from the token subject (`CurrentUser.UserId`). No request field
  (`member_id`, `user_id`, …) may be used to assume another identity. **[NOW]**

### 2.2 Organizer (group owner / creator)
- **O1** Organizer-only actions — update group, delete group, rotate invite, set exclusions, change
  participation, draw, reset, reveal — require `IsOrganizer` on the caller's membership
  (`RequireOrganizer`). **[NOW]**
- **O2** Organizer power is **scoped to the organizer's own group**. `RequireMembershipAsync`
  re-derives the caller's membership *for the target group* on every call, so an organizer of group A
  has no elevated rights in group B. **[NOW]**
- **O3** Roster/matching mutations are allowed only while the group is `Open` (`RequireOpen`); after a
  draw the organizer must `reset` first. This prevents assignment tampering after the fact. **[NOW]**
- **O4** The organizer cannot remove themselves from participation or leave without deleting the group
  (`UpdateParticipationAsync`, `LeaveAsync`), keeping every group with an accountable owner. **[NOW]**

### 2.3 Co-organizer **[FUTURE]**
- **C1** Co-organizer is a **grant on a single group**, made only by that group's organizer, and
  recorded as an audited `role_changed` event with actor, target member, and old/new role.
- **C2** Co-organizers get O1 powers **except** destructive/ownership actions reserved to the owner:
  delete group, transfer ownership, and add/remove co-organizers. These stay owner-only.
- **C3** Promoting a member to co-organizer must never disclose existing assignments; role changes on
  a drawn group do not grant retroactive visibility beyond the audited reveal (§6).
- **C4** Co-organizer grants are revocable, and revocation is itself audited.

### 2.4 Work administrator (organization tenancy) **[FUTURE]**
- **W1** Every group belongs to exactly one tenant: a personal owner **or** one organization. The
  `organization_id` is server-assigned at creation from the caller's Work membership and is
  **immutable** thereafter.
- **W2** A Work admin's authority is bounded by `organization_id`. Admin routes must filter every
  read and write by the caller's organization; there is no global admin.
- **W3** **Cross-organization access is forbidden.** A user in org X can never read or write a group,
  roster, assignment, invite, entitlement, or audit event belonging to org Y — even as a Work admin.
  This is the tenancy invariant; it is enforced in the Lambda, not by obscurity.
- **W4** Work admins manage membership and billing for their org. They do **not** by default see
  members' private wishlists/addresses or assignments; viewing an assignment still requires the
  audited emergency reveal (§6), recorded with the admin as actor and the `organization_id` on the
  event.
- **W5** Removing a user from an organization revokes their access to all of that org's groups on the
  next request (authorization is re-derived per request; no long-lived server session caches it).

---

## 3. Abuse & privacy scenarios, with mitigations

Each row: the threat, its current status, and the concrete mitigation. Rate limits referenced here
are specified in §4.

### 3.1 Invite-token leakage
- **Risk:** an invite secret ends up in a place an attacker or third party can read — browser history,
  a `Referer` header sent to an embedded image/analytics host, a CloudWatch/API Gateway access log, or
  an audit record.
- **Mitigation [NOW]:**
  - The secret is delivered **only in the URL fragment**: `…/join/{groupId}#invite={secret}`
    (`GroupService.InviteUrl`). Fragments are not sent to the server, not written to access logs, and
    stripped from the `Referer` header by browsers. The join call sends the token in the **request
    body** (`JoinGroupRequest.InviteToken`), never the query string.
  - Only the **SHA-256 hash** of the secret is persisted (`invite_hash`); the plaintext exists only in
    the single create/rotate response.
  - Comparison is constant-time (`CryptographicOperations.FixedTimeEquals`) to avoid timing oracles.
  - Rotating the invite (`RotateInviteAsync`) replaces the hash, invalidating the old secret.
- **Test:** `SecurityControlsTests.RotatedInviteDeliversSecretOnlyInUrlFragment` asserts the secret is
  absent from everything before the `#`, there is no query string, and the secret is the expected
  43-char shape.
- **Operational guard:** never log request bodies for `/join`; never add the secret to a query string
  or redirect URL. If a future email or SMS contains an invite link, it must use the fragment form.

### 3.2 Enumeration (groups, members, invites, accounts)
- **Risk:** an attacker probes IDs or tokens to discover which groups/members/emails exist, or brute-
  forces an invite.
- **Mitigation [NOW]:**
  - Group and member IDs are **unguessable GUIDs**; there are no sequential identifiers.
  - The invite secret has **256 bits** of entropy and a strict 43-char base64url format check
    (`Validation.InviteToken`); malformed and wrong-but-well-formed tokens return the **identical**
    `403 "This invitation is invalid or has expired."` — no distinguishing signal.
  - Non-membership returns `403` uniformly (`RequireMembershipAsync`).
  - Join attempts are throttled by the API Gateway stage limit (§4) to cap brute-force throughput far
    below what 256-bit entropy already makes infeasible.
- **Test:** `SecurityControlsTests.JoinRejectsMalformedAndWrongTokensWithTheIdenticalForbiddenResponse`.
- **Residual:** `RequireGroupAsync` throws `404` for a missing group vs `403` for
  "exists but you're not a member". Because group IDs are GUIDs this is not a practical enumeration
  oracle, but harmonizing both to `404` is a tracked hardening (§7). **[FUTURE hardening]**

### 3.3 Spam invitations
- **Risk:** an actor mass-generates invites or drives Humbugg to send unsolicited invitation email.
- **Status:** Humbugg does **not** send invitations by email today — the organizer copies a link. So
  there is no server-driven email-spam vector yet. Invite **rotation** is the only invite write and is
  organizer-only.
- **Mitigation [NOW]:** `RotateInviteAsync` is organizer-only and covered by the API Gateway stage
  throttle (§4).
- **[FUTURE]** When email/SMS invitations ship: server-sent invites must be rate-limited per organizer
  **and** per group, deduplicated per recipient, capped per unit time, and every send audited
  (`reminder_sent` / an `invitation_sent` action). Recipients get an unsubscribe/report path. Bounce
  and complaint feedback from the Mailer status pipeline throttles further sends.

### 3.4 Reminder abuse **[FUTURE]**
- **Risk:** reminders become a mechanism to harass a member (repeated emails) or to amplify outbound
  email volume.
- **Specification:** reminders are organizer/co-organizer-only; rate-limited per group and per actor
  (§4); deduplicated so a given member cannot be reminded more than once per cooldown; each send is
  audited (`reminder_sent`) with actor, group, and target — **but never** the recipient's address or
  message body in metadata. Reminder content is templated server-side, not free-text from the actor,
  to prevent using Humbugg as an arbitrary mailer.

### 3.5 Assignment disclosure
- **Risk:** a participant learns the full giver→recipient mapping, or another member's assignment,
  spoiling the exchange or leaking who-buys-for-whom.
- **Mitigation [NOW]:**
  - The mapping lives in `humbugg-<env>-draws`, separate from group data, and is never returned wholesale.
  - `GetAssignmentAsync` returns only the caller's own recipient.
  - Ordinary members receive other members through `Public` (id, display name, organizer/participating
    flags) — never wishlist, avoidances, or address; exclusions are returned only to organizers
    (`Detail`).
  - The only full-mapping disclosure is the audited emergency reveal (§6), which is organizer-only and
    requires a reason.
- **Test:** existing `GroupServiceSecurityTests.OrdinaryMemberSeesNoExclusionsOrPrivateParticipantData`
  and `SecurityControlsTests` reveal tests.

### 3.6 Organizer privilege escalation
- **Risk:** an ordinary member performs organizer actions, or an organizer of one group acts on
  another; or a member elevates themselves to organizer.
- **Mitigation [NOW]:** organizer state is derived from the server-side membership record for the
  *target* group on every call (O1–O2). No request field sets `is_organizer`. Participation and
  membership writes are validated against the roster (`UpdateParticipationAsync` checks the member
  belongs to the group; `SetExclusionsAsync` rejects unknown participants).
- **Tests:** `GroupServiceSecurityTests.NonOrganizerCannotRotateInvitation`, and the reveal
  authorization tests in `SecurityControlsTests`.
- **[FUTURE]** Co-organizer and Work-admin roles (C1–C4, W1–W5) extend this model; every new
  privileged route must call the same central membership/role check, never trust a client role claim.

### 3.7 Webhook forgery (payments / delivery status)
- **Risk:** an attacker forges a payment-provider webhook (to grant a paid entitlement for free) or a
  delivery-status callback.
- **Status:** the **delivery-status** path exists today and is **not** a public webhook — the status
  Lambda consumes an SQS queue fed by the Mailer platform, and the backend signs Mailer requests with
  SigV4 (`AwsSigV4MailerRequestSigner`); IAM authorizes the queue. No unauthenticated HTTP callback is
  exposed. **[NOW]**
- **[FUTURE] Payment webhooks:**
  - Verify the provider's signature (e.g. Stripe `Stripe-Signature`) against a secret held in SSM/env
    (never committed) **before** parsing the body; reject on failure with no side effects.
  - Enforce idempotency by event id; process each event at most once.
  - Treat the webhook as a *trigger to reconcile*, not as trusted state: fetch authoritative entitlement
    from the provider API keyed by the customer/subscription id, rather than trusting amounts/flags in
    the payload.
  - The webhook endpoint is exempt from Cognito auth (it has no user token) but is signature-gated and
    covered by the API Gateway stage throttle (§4); it must never accept an `entitlement`/`plan` field directly from the caller.
  - Every entitlement change is audited (`payment_entitlement_changed`) with actor = `system:payments`.

### 3.8 Entitlement tampering
- **Risk:** a user upgrades their own plan/quota without paying — e.g. by sending `plan: "work"` on
  create/update, or writing `entitlement_id`.
- **Mitigation [NOW]:** the API **never** reads `plan` or `entitlement_id` from client input.
  `CreateGroupRequest` / `UpdateGroupRequest` have no such fields; `CreateAsync` hardcodes
  `PlanCode.Free` and `entitlement_id = null`. Quotas are enforced server-side from the stored plan
  (`PlanCatalog.EnsureParticipantCapacity`), and — per rule 1 — the quota check runs on every plan.
- **Test:** existing `GroupServiceSecurityTests.ServerRejectsReactivatingAMemberAtThePlanLimit` proves
  the capacity gate is server-enforced.
- **[FUTURE]** When plan changes become possible, they may originate **only** from a verified payment
  event (§3.7) or a Work-admin action within the org, never from a group create/update body. Any field
  that could set plan/entitlement on a group mutation is a vulnerability.

### 3.9 Cross-organization access **[FUTURE]**
- **Risk:** a Work user reads/writes another organization's groups, members, invites, entitlements, or
  audit events.
- **Specification:** invariants W1–W5. Concretely: `organization_id` is server-assigned and immutable;
  every org-scoped query filters by the caller's `organization_id`; admin is per-org, never global;
  and cross-tenant reads/writes are rejected in the Lambda. Tenant isolation gets its own security-test
  suite when the feature lands (a member of org X provably cannot touch org Y's resources).

---

## 4. Rate-limit specification

Rate limiting is a **security control**, applied identically on every plan. It is enforced at the
**edge, not in application code**: API Gateway throttles the request before the Lambda is ever
invoked, so a throttled request costs no invocation and cannot exhaust Lambda concurrency.

**One uniform limit, every route.** The backend is an API Gateway **HTTP API**; its stage sets
`default_route_settings` throttling that applies to **every** route (read or write, known abuse vector
or not, including `/health`) — there are no per-route overrides. It is a token bucket protecting
aggregate throughput: a steady-state rate plus a burst capacity, defined in
`humbugg/infra/modules/compute` and tunable via `api_throttling_rate_limit` /
`api_throttling_burst_limit` (defaults **500 req/s, 1000 burst**). Over-limit requests get API
Gateway's `429`.

This is **aggregate, not per-caller**: it guards the backend from overload and smooths bursts, but a
single abusive IP can consume the shared budget (the burst caps the spike). Per-IP and pattern-based
protection is the job of the edge WAF layer below.

**Layering (AWS best practice — Well-Architected REL05-BP02 "throttle requests"):**
- **Edge — AWS WAF rate-based rules, per-IP. [FUTURE — #183]** The recommended first layer against
  unauthenticated floods, credential stuffing, and volumetric abuse. WAF does not attach to HTTP APIs,
  so it needs CloudFront-in-front-of-API or a REST-API migration; tracked in **#183**.
- **Gateway — API Gateway stage throttling, aggregate. [NOW]** Implemented here.
- **Application — per-user/tenant limits. [not implemented]** An earlier in-app ASP.NET limiter was
  removed as redundant Lambda overhead once the gateway throttle was in place. If a specific action
  ever needs a tighter or per-user bound, that is a future decision, not a default.
- **Account creation** in the identity sense (Cognito sign-up) happens before any Humbugg token
  exists, so it is throttled **upstream** at Cognito (per-IP sign-up throttles) and, once #183 lands,
  at the WAF edge.
- **Reminders** additionally need *dedup/cooldown* per recipient (a rate limit alone doesn't stop one
  member being reminded repeatedly) — see §3.4.

---

## 5. Secrets in URLs — referrer/log exposure review

Reviewed every place a secret could reach a URL:

- **Invite link** — secret in the **fragment** only (`GroupService.InviteUrl`); never path/query.
  Covered by test 3.1. ✅
- **Join request** — token in the **request body** (`JoinGroupRequest`), not the query string. ✅
- **Assignments / private data** — never placed in URLs; returned in response bodies to the entitled
  caller only. ✅
- **Cognito tokens** — sent in the `Authorization` header (Amplify/JWT bearer), never in a URL. ✅
- **Access logs** — API Gateway/CloudFront access logs record path + query, not fragments or bodies;
  because secrets live only in fragments/bodies, they are not captured. Do not enable body logging on
  `/join`. ✅
- **[FUTURE] Payment redirect URLs** — success/cancel return URLs must carry only an opaque,
  single-use, server-verified session id, never entitlement state or secrets, and the entitlement is
  granted from the verified webhook/reconciliation (§3.7), not from the redirect.

---

## 6. Review of the existing emergency-reveal audit behavior

**What it does today [NOW]** (`GroupService.RevealAsync` → `GroupRepository.RecordRevealAsync`):

- **Authorization:** organizer-only (`RequireOrganizer`); the group must be `Drawn`.
- **Reason required:** `Validation.Required(request.Reason, "reason", 500)` — a reveal cannot happen
  without a non-empty reason (≤ 500 chars).
- **Audit write:** a record is written to `humbugg-<env>-audit-events` with `group_id`, a time-ordered
  `event_id` (`{timestamp}#{guid}`), `event_type = "assignment_reveal"`, `actor_user_id`, the `reason`,
  and `created_at`. The write is `await`ed before the mapping is returned.
- **Disclosure:** only after the audit write does the method return the full giver→recipient mapping,
  and only for members still present in the group.

**Assessment — strengths:** the sensitive action is gated (organizer + drawn), always attributable
(actor + timestamp + reason), and the audit record is written **before** disclosure, so a reveal
cannot occur without a durable record. The audit event stores surrogate keys and the reason — not the
assignment contents, addresses, or the invite secret.

**Weaknesses / residual risks (see §7):**
- **R-A1** The reveal audit write is a **best-effort `PutItem`**; there is no server-side proof it is
  append-only/immutable at the data layer, and a write failure surfaces only as a `500`. Recommend the
  generalized, always-awaited, append-only audit trail being introduced in **PR #177** (related, not
  merged here) — which centralizes audit writes, redacts metadata, and makes protected-action failures
  non-swallowable. This threat model endorses adopting it for reveal and for all future privileged
  actions.
- **R-A2** The `reason` is free-text and stored verbatim. An organizer could type PII into it (e.g. a
  member's address). Under PR #177's redaction, benign-key free-text like `reason` is still stored, so
  operationally organizers should be guided not to put third-party PII in the reason. Consider a
  server-side length/however-not-content control and clear UI guidance.
- **R-A3** There is **no rate limit or alert** on reveals. A malicious organizer can reveal
  repeatedly. Mitigation: reveals are already audited; add anomaly alerting on reveal frequency (§8)
  and consider a reveal-specific rate limit.
- **R-A4** Reveal is **plan-independent** (correct per rule 1) — good; keep it that way.

---

## 7. Residual risks

| # | Residual risk | Severity | Plan |
|---|---|---|---|
| RR1 | `404` vs `403` distinction on group existence is a weak enumeration oracle | Low | Harmonize to `404`; GUID IDs keep it low-risk meanwhile |
| RR2 | No edge WAF; the aggregate API Gateway throttle is the only rate control on unauthenticated floods | Medium | Add AWS WAF per-IP rate rules (CloudFront/REST-API edge) — #183 |
| RR3 | Reveal audit is best-effort `PutItem`, not provably append-only | Medium | Adopt PR #177 generalized audit trail |
| RR4 | Reveal `reason` free-text may contain PII | Low | UI guidance; consider redaction/validation |
| RR5 | No reveal-frequency alerting | Medium | CloudWatch metric + alarm on reveal rate |
| RR6 | Fixed-window limiter allows short bursts at window edges | Low | Acceptable; move to sliding/token bucket if abused |
| RR7 | Future features (co-organizer, reminders, questions, payments, Work) not yet built to these invariants | High until built | This document is the acceptance checklist for each |
| RR8 | Payment webhook & entitlement flows unbuilt — forgery/tampering only mitigated on paper | High until built | Implement §3.7/§3.8 before any paid plan launches |

---

## 8. Operational response

- **Suspected invite leak:** organizer rotates the invite (`POST /api/groups/{id}/invite`), which
  invalidates the old secret immediately. If a group is compromised, reset the draw and/or delete the
  group. No plaintext secret is recoverable from storage (only the hash is stored).
- **Suspected assignment leak / misuse of reveal:** query `humbugg-<env>-audit-events` by `group_id` for
  `assignment_reveal` events to see actor, time, and reason. Escalate to disabling the organizer's
  account in Cognito if abuse is confirmed.
- **Credential stuffing / floods:** the API Gateway stage throttle returns `429`; add per-IP WAF rules
  (RR2, #183). Tune `api_throttling_rate_limit` / `api_throttling_burst_limit` in `humbugg/infra`
  (a Terraform apply — no image rebuild).
- **Webhook abuse [FUTURE]:** on signature-verification failures, alert and block the source IP at the
  edge; entitlements never change on an unverified event.
- **Audit integrity:** treat `humbugg-<env>-audit-events` as evidence — restrict IAM to append + read, deny
  delete/update in the table's resource policy, and consider point-in-time recovery.
- **Config tuning:** the rate limit is a Terraform variable. Emergency tightening (lower
  `api_throttling_rate_limit` / `api_throttling_burst_limit` in `humbugg/infra`) is applied via the
  deploy workflow's `run_infra` path.

---

## 9. Acceptance checklist for new features

Before shipping co-organizers, reminders, questions, payments, or Work tenancy, confirm:

- [ ] New privileged routes call the central membership/role check (O1–O2, C1–C4, W1–W5) — no client
      role claim is trusted.
- [ ] New endpoints are automatically covered by the API Gateway stage throttle (§4) — it applies to
      every route with no per-route configuration.
- [ ] No secret is ever placed in a path or query string (§5).
- [ ] Every security- or privacy-relevant action is audited with actor, target, time, and (for Work)
      `organization_id`; metadata is redacted.
- [ ] Plan/entitlement is never read from client input; changes originate only from verified payment
      or org-admin actions (§3.7–3.8).
- [ ] Cross-organization isolation has its own passing security tests (§3.9) before Work launches.
- [ ] Controls are identical across Free/Plus/Work (rule 1).
