# Humbugg data retention & deletion

Humbugg keeps your data for as long as your account and exchanges exist. There is **no automatic
expiry** of exchanges or profiles: retention is indefinite by default, and data leaves the system
only when a person or organizer deletes it, or when a legally required record reaches the end of its
own retention rule. Retention is not, and must not be advertised as, a paid plan feature — every
plan (Free, Plus, Work) is retained and deleted identically.

## What "no automatic expiry" means

- The `humbugg-prod-profiles`, `humbugg-prod-groups`, `humbugg-prod-groupmembers`, `humbugg-prod-draws`, and
  `humbugg-prod-audit-events` DynamoDB tables have **no TTL**. Nothing stamps an `expires_at` on exchange
  or profile records. (See `infra/modules/storage/main.tf` and `infra/README.md`.)
- The only TTL in the service is on `humbugg-prod-email-messages` (transactional delivery state, 90 days).
  That is an operational record, not exchange or profile content, and is intentionally left in place.

## User-controlled deletion

Three deletion capabilities exist, all initiated by the data subject or the group organizer — never
forced by an automated schedule.

### 1. Participant self-service — clear my wishlist and mailing address

`DELETE /api/groups/{groupId}/members/me/private-data`

Clears the caller's own wishlist, avoidances, mailing address, purchase claims and question threads for that exchange. The membership
itself is kept (you remain in the group); only the product-profile content you entered is erased.
Allowed whether the group is open or already drawn — it is your own data. The action is **idempotent**:
clearing already-empty fields succeeds and changes nothing. It is audited as `participant_data_cleared`.

### 2. Organizer — delete a whole group

`DELETE /api/groups/{groupId}`

Only the organizer may delete a group. The group record, its draw, and every membership are removed
in one operation. Audited as `group_deleted`.

### 3. User — request account deletion

`DELETE /api/me`

Runs entirely on the caller's own Cognito identity. There is **no organizer, Work-administrator, or
organization approval gate** — an authorized Work administrator cannot block an individual's valid
deletion request. The operation is **idempotent** and safe to retry.

## Account-deletion policy — what happens to each class of data

| Data | Treatment on account deletion |
|---|---|
| **Profile** (`humbugg-prod-profiles`) | **Deleted.** Display name and all profile fields are removed. |
| **Product-profile content** (wishlist, avoidances, mailing address) | **Deleted / anonymized** together with the membership rows below. |
| **Anonymous question threads** (#131) | **Deleted** whenever either party leaves, is removed, or erases their account, and when the group is deleted. Both ends: the thread about your own list is found by your member id, and the one you opened is found by inverting the draw — a thread stores no giver, so that inversion is the only way to reach it. A reset does not delete them but makes them unreachable: the thread id contains the draw id. |
| **Purchase claims** (which gifts you marked planned or bought, #130) | **Deleted / anonymized** with the membership row they live on — they are stored on the claimant's own row, so no separate sweep exists or is needed. Also cleared by the self-service control below. |
| **Groups the user organizes** | **Deleted in full** — memberships, draw, and group record. Other members lose the group; this is the defined trade-off for organizer deletion (Humbugg does not auto-transfer ownership). |
| **Memberships in groups the user only participates in — open group** | **Deleted.** The row is removed and any exclusion pair referencing it is cleaned up. |
| **Memberships in groups the user only participates in — completed draw** | **Anonymized, not deleted.** The row is kept (its `member_id` is referenced by the completed draw) but `user_id` is repointed to an irreversible pseudonym and the display name, wishlist, avoidances, address, purchase claims and question threads are erased. This preserves the integrity of a draw other people already rely on while removing the personal data behind it. |
| **Completed draws** (`humbugg-prod-draws`) | **Left intact** where the group survives (giver→recipient mapping stays valid against the anonymized membership row); **deleted** with the group when the deleting user was the organizer. |
| **Audit trail** (`humbugg-prod-audit-events`) | **Never deleted.** The append-only trail (what happened, to what, when, correlation id, redacted metadata) is preserved. Only the **actor reference** is anonymized: `actor_user_id` is rewritten from the Cognito subject to the same irreversible pseudonym across every record the user authored. This is the single, deliberately narrow mutation allowed on audit records (`IAuditActorAnonymizer`); the append-only write path (`IAuditRepository`) is untouched. |
| **Organizations / Work membership** | The user's link to any organization is severed by the membership handling above and by actor anonymization in the audit trail. Deletion does not require, and cannot be blocked by, an organization administrator. |
| **Billing / financial records** | **Retained, separated from product-profile data.** Required financial records (invoices, payment/entitlement history) are kept under their own legal retention obligation and are **not** part of the product-profile store this flow erases. Deletion anonymizes the person's link to them (via audit actor anonymization); it never erases the financial record itself. Humbugg does not currently persist a first-party billing ledger in DynamoDB — see the Maintainer TODOs in the PR for confirming the retention rule and the store of record for financial data. |

### The pseudonym

The anonymized identity is `deleted-user-<first 24 hex of SHA-256(user_id)>`. It is:

- **Deterministic** — every record for the same user maps to one anonymized identity, and retries
  converge on the same value (this is part of what makes the operation idempotent);
- **One-way** — a SHA-256 digest cannot be resolved back to the original Cognito subject.

## Idempotency

Account deletion is safe to run more than once (retries, at-least-once delivery, crash recovery):

- Profile deletion is an unconditional delete — removing an already-absent profile is a no-op.
- Membership removal/anonymization repoints `user_id` off the real subject, so a second run no longer
  finds the rows through the `user_id` index.
- Actor anonymization only ever moves records off the real subject; a second run finds nothing left
  to rewrite. It is deliberately re-run on every attempt so a crash between the terminal audit write
  and anonymization still self-heals.
- The terminal `account_deleted` audit event is recorded only when there was something to delete, so a
  pure no-op retry does not append duplicate events.

Behavior is covered by unit tests in `backend/Humbugg.Api.Tests/AccountDeletionTests.cs`.

## Product copy

No plan, pricing, or marketing copy advertises retention ("stored forever", "we keep your data",
etc.) as a feature. Retention is a baseline property of the service, identical on every plan.
