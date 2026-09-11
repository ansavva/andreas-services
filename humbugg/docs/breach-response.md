# Humbugg breach response (GDPR Art. 33/34)

The runbook `gdpr-compliance.md` §8 promised and tracked under #191. Written for one person
operating Humbugg. Cross-linked from [`gdpr-compliance.md`](gdpr-compliance.md) §8/§9,
[`threat-model.md`](threat-model.md) §8, and [`runbooks.md`](runbooks.md).

This is a **detection → triage → containment → notification → record → review** runbook, not
legal advice. Nothing here substitutes for counsel on an actual incident (`gdpr-compliance.md`
top-of-file note applies here too).

---

## 1. Detection signals

None of these are breach *proof* by themselves — each is a reason to open triage (§2).

| Signal | Where | What it might mean |
|---|---|---|
| `humbugg-prod-api-errors` / `-api-5xx` alarming repeatedly, off a normal deploy pattern | `runbooks.md` §7 | Exploitation attempt against the API, or a bug leaking data through an error path. |
| A burst of `assignment_reveal` events in `humbugg-prod-audit-events` — more reveals than organizers, or reveals clustered in a short window across unrelated groups | Manual query, below | Compromised organizer credentials, or a code path disclosing assignments outside the intended reveal flow. |
| A burst of any other sensitive event type (`participant_removed`, `role_changed`, `payment_entitlement_changed`) concentrated on one actor or one short window | Same | Account takeover, or an authorization bug. |
| WAF rate-limit blocks | **Not yet live** — tracked as #183 (`threat-model.md` §4/RR2); once deployed, a sustained spike in blocks is a credential-stuffing or enumeration signal. Until then this signal does not exist — do not expect it. | |
| A processor breach notice | AWS, Stripe, or Google Workspace emailing about their own incident | Their breach may expose data Humbugg gave them (categories 1, 9 in `gdpr-compliance.md` §1/§7) even though Humbugg's own systems are untouched. |
| A user or organizer report of suspicious activity (seeing data they should not, a stranger in their exchange) | `support@humbugg.com` | Any of the above; treat as credible until ruled out. |

**Querying the audit trail for anomalies.** `humbugg-prod-audit-events` is partitioned by
`group_id` with no secondary index (`humbugg/infra/README.md`), so there is no cheap
cross-group query — a genuine "all `assignment_reveal` events this week, any group" search is
a full `Scan`, which is expensive and reads every record. Use it deliberately, not as routine
monitoring:

```bash
aws dynamodb scan \
  --table-name humbugg-prod-audit-events \
  --filter-expression "event_type = :t AND created_at > :since" \
  --expression-attribute-values '{":t":{"S":"assignment_reveal"},":since":{"S":"2026-09-01T00:00:00Z"}}' \
  --projection-expression "group_id, event_id, actor_user_id, created_at, reason"
```

For a single suspect group, the cheap form is a direct `Query` on its `group_id`
(`threat-model.md` §8). Records never contain the assignment contents, addresses, or invite
secrets themselves (`AuditRedaction` — `humbugg/infra/README.md`), so this query cannot itself
leak the personal data under investigation.

---

## 2. Severity triage

| Severity | Criteria | Example |
|---|---|---|
| **Low** | No personal data exposed, or exposure confined to data the affected person can already see (their own). | A bug returning a member their own stale cached data. |
| **Medium** | Personal data of a small, identifiable set of people exposed to unauthorized parties within Humbugg's own user base (not the public internet); contained quickly. | An organizer's compromised credentials used to reveal one group's assignments before being caught. |
| **High** | Personal data exposed to the public internet, or to a large/unbounded set of people, or of a kind listed as high-risk in §5 (assignments, addresses, wishlists) at any scale. | A misconfigured S3 bucket or DynamoDB export made public; a code bug returning another user's private data broadly. |

Severity drives urgency, not whether the 72-hour clock runs — see §3.

---

## 3. The 72-hour clock

**Art. 33** requires notifying the supervisory authority within 72 hours of "becoming aware"
of a qualifying breach (personal data breach with a risk to rights and freedoms — not every
security bug qualifies; a contained low-severity issue with no realistic exposure may not).

- **Who starts it**: the operator, the moment they have a reasonable degree of certainty a
  personal-data breach occurred — not certainty about full scope. A credible report or a
  detection signal from §1 that survives a first look (§2 triage above **Low**) starts the
  clock; waiting for a complete investigation before starting it is the wrong order.
- **What "aware" means**: enough to say *something* happened involving personal data, even if
  you do not yet know its full extent. "Aware" is not "fully understood" — under-informed
  notification followed by a supplementary one is the correct pattern, not delayed
  notification.
- **The clock does not pause** for triage, containment, or figuring out what to say. Start
  containment (§4) immediately and draft the notification (§6) in parallel, not after.

Record the moment of awareness — the timestamp you decided "yes, this is a breach" — in the
Art. 33(5) register (§7) even if notification turns out not to be required in the end.

---

## 4. Containment, per asset

Work through whichever of these apply; do not wait to finish investigating before containing.

| Asset | Containment action |
|---|---|
| A group's invite link | Organizer rotates it: `POST /api/groups/{id}/invite` (self-service, invalidates the old secret immediately — `threat-model.md` §3.1). If the organizer is unreachable, this cannot be done on their behalf; there is no admin override (by design, per `runbooks.md` §4). |
| A specific compromised account | Disable it in Cognito so it cannot authenticate while you investigate: `aws cognito-idp admin-disable-user --user-pool-id $(aws ssm get-parameter --name /humbugg/prod/cognito-user-pool-id --query Parameter.Value --output text) --username <sub>`. This blocks sign-in without deleting data, so the account and its history remain available for investigation. |
| Stripe secret key / webhook secret | Roll per `stripe-setup.md` §5 — this is the fastest way to cut off a compromised key, ahead of any scheduled rotation. |
| The operator's AWS IAM access key | `aws iam create-access-key` for a replacement, switch your credentials to it, confirm with `aws sts get-caller-identity`, then `aws iam delete-access-key --access-key-id <compromised-id>` to revoke the old one immediately (root `CLAUDE.md` "Environment access"). Do this first if the key itself is the suspected compromise — everything else in this table depends on holding a working key. |
| A misconfigured public resource (bucket, table export) | Fix through Terraform + the deploy pipeline where possible (root `CLAUDE.md` "prefer fixing infrastructure through Terraform... over manual CLI mutations"); a manual CLI lockdown is acceptable as an immediate stopgap ahead of the Terraform fix when public exposure is ongoing. |
| A vulnerable code path | Roll back per `runbooks.md` §7 "Rollback" if the last-good commit predates the bug; otherwise ship a fix through the normal PR/deploy path — there is no hotfix-without-review path in this repo, and none should be added under incident pressure. |

---

## 5. The Art. 34 decision: does this also need to notify data subjects?

Art. 34 requires notifying affected individuals directly when the breach is likely to result
in a **high risk** to their rights and freedoms — a higher bar than Art. 33's authority
notification, which applies whenever there is *a* risk.

| Data category exposed | High risk to the individual (Art. 34 applies)? |
|---|---|
| Assignments (giver → recipient mapping) | **Yes.** Spoils the exchange for the people involved — the entire reason the reveal flow is audited and gated (`threat-model.md` §3.5, §6). |
| Mailing addresses | **Yes.** Physical-world exposure. |
| Wishlists / avoidances | **Yes** if tied to an identifiable person — the point of a Secret Santa wishlist is that it stays between the exchange and the giver. |
| Account credentials / tokens | **Yes.** Direct account-takeover risk. |
| Aggregated product-analytics counts (`humbugg-prod-analytics-events`) | **No.** Structurally contains no PII — no wishlist text, address, email, token, or assignment can reach this table by construction (`gdpr-compliance.md` §1, `docs/analytics.md`). An exposure here is not a personal-data breach at all. |
| Audit-trail metadata (actor id, action, target surrogate key) | **Generally no** on its own — it is redacted of sensitive values (`AuditRedaction`) — but treat as **yes** if the exposure lets someone correlate actor identities to the high-risk categories above (e.g. combined with a separate leak). |

When in doubt between Medium/High severity (§2) and this table says the exposed category is
high-risk, notify — the cost of an unnecessary notification is far lower than the cost of a
missed one.

---

## 6. Notification templates

Both carry placeholders. **Contact of record**: `support@humbugg.com`. **Legal entity name**:
still a placeholder in this repo (`gdpr-compliance.md` §"Controller" — "registered business
name TBD") — fill in the real registered entity name before sending either notification; do
not send with `[LEGAL ENTITY NAME]` still in it.

### To the supervisory authority (Art. 33)

```text
Subject: Personal data breach notification — Humbugg

Controller: [LEGAL ENTITY NAME], operating Humbugg (https://www.humbugg.com)
Contact: support@humbugg.com

Nature of the breach:
  [What happened, in plain terms — e.g. "an authorization bug allowed a subset of
  users to view another user's X"]

Categories and approximate number of data subjects affected:
  [e.g. "approximately N accounts; data categories: [assignments / addresses /
  wishlists / account credentials — per §5 above]"]

Categories and approximate volume of personal data records affected:
  [e.g. "N group memberships, N mailing addresses"]

Likely consequences:
  [e.g. "spoiled gift exchanges for affected groups"; "potential for physical-world
  harm via exposed addresses" if applicable]

Measures taken or proposed:
  [Containment steps from §4 already taken; planned remediation]

Date/time the controller became aware:
  [Timestamp from §3]

This notification is submitted within 72 hours of becoming aware per Art. 33(1).
[If not all information is yet available: "This is a preliminary notification per
Art. 33(4); a supplementary notification with full details will follow."]
```

### To affected data subjects (Art. 34)

```text
Subject: Important notice about your Humbugg data

We're writing to let you know about a security incident that may have affected your
data on Humbugg.

What happened:
  [Plain-language description, no jargon]

What information was involved:
  [Specific to what was exposed for this recipient — e.g. "your mailing address" —
  never a generic list that overstates or understates their own exposure]

What we're doing about it:
  [Containment + remediation summary]

What you can do:
  [Concrete, specific actions — e.g. "we recommend changing your password if you
  reuse it elsewhere"; only include steps that are actually relevant]

Questions? Contact us at support@humbugg.com.

— [LEGAL ENTITY NAME] / The Humbugg team
```

---

## 7. The Art. 33(5) register

Art. 33(5) requires documenting **every** breach, including ones never notified to the
authority or data subjects — facts, effects, and remedial action taken.

**This register is a private record and does not live in this public repository.** Do not
create a breach log file, issue, or commit in `andreas-services` describing a real incident's
details — this repo is public (`stripe-setup.md` §6 makes the same point about the Stripe
account owner's address, for the same reason). Keep the register wherever the operator keeps
other private operational records outside this repo (e.g. a private document store) — this
runbook deliberately does not invent a URL for one, because none is set up yet; if you are
the first person to use this runbook for a real incident, that is the first thing to create,
privately.

Each entry should record: date/time of the breach and of becoming aware, what happened,
categories and volume of data affected, whether Art. 33/34 notification was sent (and to whom,
when), containment actions taken (§4), and the outcome of the post-incident review (§8).

---

## 8. Post-incident review

After containment and any required notification:

1. Confirm the root cause is actually fixed, not just contained (a rolled-back deploy is
   containment; the underlying bug still needs a real fix and a test).
2. Check whether an existing control should have caught this sooner — an alarm that should
   exist and doesn't (`runbooks.md` §7), an authorization invariant that should have blocked
   the access (`threat-model.md` §2), or a rate limit that should have slowed it (`threat-model.md`
   §4).
3. Update the register entry (§7) with the outcome.
4. If the review surfaces a gap worth fixing in this repo (a missing alarm, a missing test, a
   documentation gap), open a GitHub issue for it — the incident itself stays in the private
   register, but a structural fix is ordinary repo work.
