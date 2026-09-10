# Humbugg GDPR compliance & gap analysis

This document maps Humbugg's processing of personal data to the EU/UK General Data Protection
Regulation and records where the service is compliant today and where a gap remains. It doubles as
Humbugg's **Record of Processing Activities** (Art. 30) and links each open gap to the issue that
closes it.

> **Status:** Humbugg is pre-launch with **no real production users** yet. This is the moment to fix
> the posture cheaply. Several remediation items below are documentation/records tasks rather than
> code. Nothing here is legal advice — the policy copy and this analysis should be reviewed by
> counsel before public launch (see `humbugg/marketing/src/config/policies` maintainer note).

- **Controller:** the Humbugg operating entity (registered business name TBD — placeholder
  `Humbugg` in `frontend/src/config/policies`; confirm before launch).
- **Privacy contact / point of contact:** `support@humbugg.com`. Humbugg's scale does not trigger the
  mandatory-DPO test in Art. 37 (no large-scale monitoring or special-category data as a core
  activity); the privacy contact serves the DPO-style role. Revisit if scale or data categories change.
- **Launch market:** United States, priced in USD. GDPR still applies to any EEA/UK data subjects who
  use the service (Art. 3(2)), so the service is built to GDPR standards from day one.

---

## 1. Data inventory / data map

Every category of personal data Humbugg holds, where it lives, and its retention. Storage is DynamoDB
unless noted. Retention is **indefinite by default** (`docs/data-retention-deletion.md`) — data leaves
the system on user/organizer action or when a legal record reaches the end of its own rule.

| # | Data category | Fields | Store | Source | Retention |
|---|---|---|---|---|---|
| 1 | **Account / identity** | Cognito subject (`sub`), email, password (hashed by Cognito), confirmation status | AWS Cognito User Pool | User at signup | Life of account; erased/disabled on account deletion |
| 2 | **Profile** | `display_name`, timestamps | `humbugg-prod-profiles` | User | Life of account; **deleted** on account deletion |
| 3 | **Membership / exchange content** | `display_name`, **wishlist**, **avoidances**, **mailing address**, role, participation flag | `humbugg-prod-groupmembers` | The member (their own authored content) | Life of group; **deleted** (open group) or **anonymized** (drawn group) on account deletion, or cleared on demand via `DELETE /api/groups/{id}/members/me/private-data` |
| 4 | **Group metadata** | Group name, description, dates, spending limit, exclusion pairs (member-id references), owner id | `humbugg-prod-groups` | Organizer | Life of group; deleted with the group |
| 5 | **Draw / assignment** | giver `member_id` → recipient `member_id` map | `humbugg-prod-draws` | Matching engine (server) | Life of group; kept valid against anonymized rows so a completed draw survives a participant's deletion |
| 6 | **Audit trail** | action, target, actor `user_id`, correlation id, redacted metadata, timestamp | `humbugg-prod-audit-events` | Server (append-only) | **Never deleted**; on account deletion only the `actor_user_id` is anonymized to an irreversible pseudonym (`IAuditActorAnonymizer`) |
| 7 | **Product analytics** | `event_type`, `plan`, `group_id` surrogate, timestamp, allow-listed aggregate dimensions | `humbugg-prod-analytics-events` | Server (`GroupService`) | Retained; **contains no PII by construction** — wishlist/address/email/token/assignment are structurally impossible to record (`docs/analytics.md`) |
| 8 | **Transactional email metadata** | message id, recipient reference, delivery state | `humbugg-prod-email-messages` | Email pipeline | **90-day TTL** (only TTL in the service) |
| 9 | **Billing / customer records** | Stripe customer id, payment/entitlement history, invoices | **Stripe** (test mode today; live is #159) | Stripe checkout | Under Stripe + financial-record retention; **not** in the product-profile store; deletion anonymizes the link, never erases the financial record |
| 10 | **Client-side storage** | Cognito tokens (`localStorage` on web, the OS keychain on a device); functional `sessionStorage` keys; a Plus purchase intent (`AsyncStorage`) | User's browser or device | Product app | Session / until sign-out, purchase resolution, or cleared — see §6 |

Humbugg does **not** collect special-category data (Art. 9) and does not knowingly serve children.

---

## 2. Lawful basis per processing activity (Art. 6)

| Processing activity | Lawful basis | Notes |
|---|---|---|
| Create/operate an account, run exchanges, produce assignments | **Contract** (Art. 6(1)(b)) | Core service the user signed up for |
| Store the wishlist / avoidances / mailing address a member enters | **Contract** | Necessary to deliver the gift exchange |
| **Transactional / essential email** (email confirmation, password reset, "you've been invited", "your assignment is ready") | **Contract** | Muting these would break the core flow; always sent regardless of preferences (#187 classification) |
| **Non-essential email** (reminders, activity notifications, product news) | **Consent** (Art. 6(1)(a)) / opt-out | Governed by the per-user toggle in #187; user can withdraw at any time |
| Terms & Privacy acceptance at signup | **Consent evidenced** (Art. 7) | Recorded server-side with policy version + timestamp (#188) |
| Security **audit trail** | **Legitimate interest** (Art. 6(1)(f)) — security, fraud prevention, accountability | Minimized + redacted; balancing favors retention because it protects all participants |
| **Product analytics** | **Legitimate interest** (Art. 6(1)(f)) — improving the service | PII-free aggregate counts only; negligible impact on the data subject, so the balancing test passes and no consent banner is required (§6) |
| **Billing** via Stripe | **Contract** + **legal obligation** (Art. 6(1)(c)) for financial records | Financial records retained under their own legal rule |

---

## 3. Data-subject rights (Ch. III)

| Right | How Humbugg serves it | Status |
|---|---|---|
| **Access** (Art. 15) | `GET /api/me/export` returns the caller's own data as portable JSON (`MeController` → `DataExportService`) | ✅ **Shipped in this issue (#189).** UI download button is a follow-up until the settings page (#186) lands — see §9 |
| **Portability** (Art. 20) | Same export endpoint — structured, machine-readable JSON, provided directly to the data subject | ✅ Shipped (#189) |
| **Rectification** (Art. 16) | Display name via `PUT /api/me`; wishlist/avoidances/address via `PATCH /api/groups/{id}/members/me`. Email/password are Cognito-managed (password reset, email change flows) | ✅ Self-service for product data; non-self-service identity changes documented via DSAR intake (#192) |
| **Erasure** (Art. 17) | `DELETE /api/me` → `AccountDeletionService`; per-exchange clear via `DELETE /api/groups/{id}/members/me/private-data`; rules in `docs/data-retention-deletion.md`; audit-actor anonymization (#182, #177) | ✅ Shipped |
| **Restriction** (Art. 18) | Manual intake at `SUPPORT_EMAIL` (`config/policies.ts`); documented on the Privacy Policy ("Requesting restriction or objection", under "Your choices") and below | ✅ Documented — **#192** |
| **Objection** (Art. 21) | Objection to non-essential email = the opt-out toggle (#187). No profiling for marketing. Other objections go through the same manual intake as restriction | ✅ Covered by #187 + documented DSAR intake **#192** |
| **Automated decision-making** (Art. 22) | The **matching engine** (`MatchingService`) assigns givers to recipients automatically | ✅ **Not** Art. 22 territory — see below |

### Manual intake: restriction and objection (#192)

Access, rectification, erasure, and export are self-service, in-product. Restriction (Art. 18),
objection (Art. 21), and any change that is not self-service — an email or identity change, chiefly
— go to `SUPPORT_EMAIL` (`config/policies.ts`), and the Privacy Policy documents this under "Your
choices" → "Requesting restriction or objection". Humbugg may ask the requester to confirm from the
account's own email address before acting, to keep the same request from a spoofed sender from
changing someone else's account. The response commitment mirrors Art. 12(3): within one month,
extendable by two further months for a complex request, with notice of the extension. There is no
ticketing system yet — the mailbox itself is the intake, which is adequate at pre-launch volume and
should be revisited if request volume grows past what one inbox can track.

### The matching engine and Art. 22

The matching engine is fully automated, but it does **not** produce a "legal or similarly
significant effect" on a person: it assigns who buys whom a gift within a group the user chose to
join. It uses only membership and organizer-defined exclusions — no profiling, no scoring of the
person, no special-category inputs. It therefore falls outside the Art. 22 prohibition on solely
automated decisions with significant effects. For transparency the Privacy Policy still describes,
in plain language, that assignments are generated automatically and that organizers can set
exclusions and re-draw. No human-review workflow is required for a Secret-Santa assignment.

---

## 4. Consent management (Art. 7)

- **Terms & Privacy consent at account creation (#188).** An active, unchecked-by-default checkbox
  agreeing to the current Terms and Privacy Policy gates the **profile-setup form**, which is the
  first screen a new account reaches and one it cannot get past — the backend rejects a first
  profile save that carries no valid consent. The checkbox sat on the signup form until sign-up
  became a Cognito hosted page, which cannot carry Humbugg's own terms (#365). Consent is recorded
  server-side with at
  minimum the **policy version** and a **UTC timestamp** associated with the user, so it can be
  evidenced (Art. 7(1)). The policy version references `POLICY_VERSION` in
  `frontend/src/config/policies` so it stays in sync when policies change. The data export (#189)
  surfaces the recorded consent — the field is reserved in the export DTO (`ExportedProfile.consent`)
  and populated once #188 lands; the export's `consent` shape (`policy_version` + `agreed_at`) is the
  coordinated field naming.
- **Non-essential email opt-out (#187).** A single per-user preference (`non_essential_emails_enabled`,
  default **on**) governs reminders/activity/product-news email. Withdrawing consent is as easy as
  giving it (Art. 7(3)). Essential email ignores the toggle. The preference is reserved in the export
  DTO (`ExportedProfile.non_essential_emails_enabled`) and exported once #187 lands.
- **No pre-ticked boxes, no bundled consent.** Contract-basis processing is not dressed up as consent;
  consent is used only where it is the correct basis (non-essential email).

---

## 5. Records of processing (Art. 30)

Sections 1 (data map), 2 (lawful bases), 9 (processors) and the retention column together constitute
Humbugg's Article 30 record: categories of data subjects and personal data, purposes, lawful bases,
recipients/processors, international transfers, retention periods, and a reference to the technical &
organizational security measures (`docs/threat-model.md`, IAM least-privilege, encryption at rest via
AWS-managed keys, TLS in transit, the append-only audit trail, and the analytics allow-list). This
document is the living RoPA and should be updated whenever a new processing activity, processor, or
data category is added.

---

## 6. Cookies, local storage & analytics-consent audit

Humbugg sets **no advertising or third-party tracking cookies** and runs **no client-side analytics
SDK**. What the SPA stores:

| Key / store | Purpose | Category | Lifetime |
|---|---|---|---|
| Cognito tokens (`humbugg.auth.*` in `localStorage` on web, `expo-secure-store` on a device) | Keep the user signed in; authorize API calls | **Strictly necessary** | Until sign-out / token expiry |
| `humbugg:returnTo` (`sessionStorage`) | Return the user to their destination after auth | Functional | Tab session |
| `humbugg:oauthVerifier`, `humbugg:oauthState` (`sessionStorage`) | Carry the PKCE verifier and CSRF state across the redirect to the hosted sign-in page | **Strictly necessary** | Deleted at the end of the sign-in it belongs to |
| `humbugg:join:{groupId}` (`sessionStorage`) | Preserve an invite token through the sign-in redirect | Functional | Tab session |
| `humbugg:invite:{groupId}` (`sessionStorage`) | Remember a freshly minted invite URL in the organizer view | Functional | Tab session |
| `humbugg.plus.intent` (`AsyncStorage`, persists across tab close) | Remember a Plus purchase in progress across the Stripe Checkout round trip | Functional | Cleared when the purchase resolves |

The marketing site (`www.humbugg.com`) sets **nothing** — verified by grepping `humbugg/marketing`
for `cookie`/`localStorage`/`sessionStorage`, zero hits. Everything in the table above belongs to the
product app.

**Consent-banner assessment:** under the ePrivacy Directive/PECR, storage that is *strictly necessary*
to provide a service the user explicitly requested does not require prior consent, and neither do the
functional keys above (all first-party, no cross-site tracking). Product analytics is emitted
**server-side** and is PII-free by construction (`docs/analytics.md`), so it sets nothing on the device
and needs no analytics-consent banner. **Conclusion: no cookie-consent banner is required** for the
current design. If Humbugg ever adds non-essential cookies or a client analytics SDK, a consent
mechanism becomes mandatory and this assessment must be revisited.

**Transparency: done.** The Privacy Policy now discloses this table verbatim under "Cookies and local
storage" (`marketing/src/pages/PrivacyPage.tsx`) — **#192 closed**.

---

## 7. Processors & international transfers

| Processor | Services used | Personal data | DPA / transfer mechanism |
|---|---|---|---|
| **Amazon Web Services, Inc. (AWS)** | Hosting, authentication (Cognito), database (DynamoDB), file storage (S3), transactional email (SES) | Account identifiers, verified email address, exchange content, wish lists, addresses, audit records (categories 1-8, 10 above) | AWS GDPR Data Processing Addendum, incorporated in the AWS Service Terms, with EU Standard Contractual Clauses; UK Addendum |
| **Stripe, Inc.** | Payment processing for Plus | Name, email, billing details as entered on Stripe Checkout — Humbugg never stores card data (category 9) | Stripe Data Processing Agreement, incorporated in the Stripe Services Agreement, with SCCs |
| **Google LLC (Google Workspace)** | The support mailbox `support@humbugg.com` | Whatever a data subject sends to support | Google Workspace Data Processing Addendum, SCCs |

All three are published on the **[Sub-processors](../marketing/src/pages/SubProcessorsPage.tsx)**
page (`/sub-processors`), reachable from the Privacy Policy's "How we share information" section and
the new "Cookies and local storage" section. Each is bound by an Art. 28 DPA incorporating the EU
Standard Contractual Clauses. **Residency posture:** the product stack runs in `us-east-1` — every
AWS-held category above is a US transfer covered by the AWS DPA's SCCs / UK Addendum; there is no
secondary AWS region and no data residency choice offered to the user today. No personal data is sent
to any processor outside this list.

**Operator checklist — record before public launch (the page and this table describe the mechanism;
these are the actual executed-agreement records, still outstanding):**

- [ ] AWS DPA acceptance recorded (AWS Artifact / Service Terms, date, by whom)
- [ ] Stripe DPA (Services Agreement §, date)
- [ ] Google Workspace DPA (Admin console, date)

Publishing the list itself is **done** (#190's page); the checklist above — the record of *when* and
*by whom* each DPA was actually accepted — remains open, so #190 stays open until an operator fills
it in.

---

## 8. Breach notification (Art. 33/34)

Humbugg has the raw materials for detection — the append-only audit trail, CloudWatch, and processor
breach notices from AWS/Stripe — and a threat model (`docs/threat-model.md`), but **no written breach
runbook yet**. Required posture:

- **Art. 33:** notify the supervisory authority within **72 hours** of becoming aware of a qualifying
  breach.
- **Art. 34:** notify affected data subjects without undue delay when the breach is likely to result in
  a **high risk** to their rights and freedoms.
- **Art. 33(5):** keep an internal record of **every** breach, including ones not notified.

A detection/triage/notification runbook (`docs/breach-response.md`), notification templates, and the
minimum alerting to actually detect a breach are tracked in **#191**. The privacy contact of record is
`support@humbugg.com`.

---

## 9. Remediation checklist

| Gap | Owner issue | Status |
|---|---|---|
| Right of access / portability — self-service export | **#189 (this issue)** | ✅ `GET /api/me/export` shipped with tests |
| Erasure (account + per-exchange) | shipped previously (#182/#177) | ✅ Done |
| "Download my data" button on the settings page | **#186** (settings page) | ⏳ Endpoint + typed client method (`api.exportMyData`) ready; button added when #186 merges |
| Terms/Privacy consent recorded at signup, surfaced in export | **#188** | ⏳ Export DTO field `consent` reserved; populated when #188 lands |
| Non-essential email opt-out, surfaced in export | **#187** | ⏳ Export DTO field `non_essential_emails_enabled` reserved; populated when #187 lands |
| Sub-processor list published + transfer mechanism pinned | **#190** | ✅ `/sub-processors` page shipped. ⏳ Operator checklist (§7) — DPA acceptance dates/by-whom — still outstanding, so the issue stays open |
| Breach detection & notification runbook (Art. 33/34) | **#191 (new)** | 🔲 Filed |
| Cookies/local-storage disclosure + manual DSAR intake (restriction/objection) | **#192** | ✅ Done — Privacy Policy §8 "Cookies and local storage" + §13 "Requesting restriction or objection" |
| Appoint/confirm privacy contact; confirm legal entity name in policies | tracked in `config/policies` maintainer note | 🔲 Pre-launch |

### The data export (this issue)

`GET /api/me/export` (`MeController.Export` → `DataExportService`) returns the caller's own personal
data as portable JSON with a `Content-Disposition: attachment` hint:

- **profile** — `user_id`, `display_name`, `email` (from the access token when present — Cognito access
  tokens do not carry `email` by default, so it may be omitted with a note), timestamps, and reserved
  fields for `avatar` (#186), `non_essential_emails_enabled` (#187), and `consent` (#188);
- **memberships** — for each group the caller belongs to: group name/status, their role, participation
  flag, and the **wishlist / avoidances / mailing address they themselves authored**, plus timestamps.

By design it **never** includes another member's personal data, the group's other members, the
exclusion matrix, or any draw assignment — in particular it never reveals whom the caller was assigned
to give to, because that recipient's data belongs to the recipient. It runs on the caller's own Cognito
identity with no admin gate and is read-only, so it is safe to call repeatedly. Behavior is covered by
`backend/Humbugg.Api.Tests/DataExportTests.cs`, including a test that serializes the export and asserts
no other member's PII or assignment data appears anywhere in the document.
