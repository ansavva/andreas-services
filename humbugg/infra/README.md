# Humbugg infrastructure

Terraform owns Humbugg infrastructure.

- `envs/prod` owns the production Cognito pool, DynamoDB tables, Lambda/ECR,
  API Gateway, S3, CloudFront, the service-specific `humbugg.com` certificate,
  and Route53 aliases in the existing `humbugg.com` zone.
- `envs/dev` creates one isolated Cognito pool, S3 bucket, and set of DynamoDB
  tables per generated machine UUID.
- Production state is stored at `humbugg/prod/terraform.tfstate`. Development
  state is isolated at `humbugg/dev/<account-id>/<machine-uuid>/terraform.tfstate`.

The API exposes public `GET /health` and protects `/api/*` with a Cognito JWT
authorizer. CloudFront serves all browser routes from the SPA and proxies
`/api/*` and `/health` to API Gateway.

Apply production infrastructure through GitHub workflows. Provision local
development infrastructure only through `scripts/dev-aws-setup.sh`, which
selects the correct per-machine state key and Terraform variables.

The marketing distribution serves only `https://www.humbugg.com` as canonical.
Viewer requests for the apex `humbugg.com` receive a permanent `308` redirect
with the original path and raw query string. Redirect behavior is tested locally
and in the PR workflow; the production workflow also verifies the apex redirect
after deployment.

## Audit trail

`humbugg-prod-audit-events` is the standard, append-only audit log for security- and
privacy-relevant exchange actions on **every** plan (Free, Plus, and Work — auditing is
never gated on a plan). The application records an event for group creation/deletion and
updates, participant joins/leaves/removals and participation changes, exclusion changes,
invite rotation, draws and resets, and emergency assignment reveals. The model also defines
`reminder_sent`, `role_changed`, and `payment_entitlement_changed` actions so those events
are audited the moment those product features ship (see the Maintainer TODOs in the PR).

Every record identifies the **actor** (`actor_user_id`), **action**, **target**
(`target_type` + `target_id`, always a surrogate key), **group** (`group_id`, the partition
key) or organization (`organization_id`), **timestamp** (`created_at`), and the request
**correlation id** (`correlation_id`).

**Redaction.** Records never contain sensitive values, addresses, invite secrets, tokens, or
assignment contents. All metadata passes through `AuditRedaction` (in
`Humbugg.Api/Services/AuditTrail.cs`) before persistence: any key that names a sensitive
field, and any value that looks like an invite link or high-entropy token, is replaced with
`[redacted]`. This is enforced in code and covered by `AuditTrailTests`.

**Append-only.** The application has no update or delete code path for audit records:
`IAuditRepository` exposes only `AppendAsync`, and each write uses a DynamoDB
`attribute_not_exists` condition so an existing `(group_id, event_id)` record can never be
overwritten. Writes are awaited and their failures propagate — an audited action cannot
silently lose its audit record. Infra reinforces durability with point-in-time recovery and
table `deletion_protection_enabled`. The Lambda's shared DynamoDB IAM policy still grants
broad table actions, so append-only is an application guarantee, not an IAM one.

**Internal access.** Reads are operational only. Engineers with the appropriate IAM
permissions can inspect records through the DynamoDB console or API in the production
account; there is no product or API surface that returns audit records. Access is governed by
the same account IAM/SSO controls as every other production DynamoDB table.

**Retention.** Retention is intentionally indefinite: the table has **no TTL**, so records are
never expired automatically (unlike `humbugg-prod-email-messages`, which expires after 90 days).
Point-in-time recovery retains a 35-day continuous backup window for restore. A maintainer who
later adopts a fixed retention policy should add a `ttl` block on an `expires_at` attribute and
have the application stamp it — see the Maintainer TODOs in the PR.

## Product analytics

`humbugg-prod-analytics-events` stores the **privacy-safe product-analytics funnel** — a stream separate
from the security audit trail. Events record only `plan`, a `group_id` surrogate key, an
`idempotency_key`, `occurred_at`, and an allow-listed map of aggregate dimensions (counts, plan
codes, day spans). Wishlist text, addresses, email addresses, invite tokens, and assignments are
structurally impossible to record; the `AnalyticsDimensions` allow-list (which reuses the audit
`AuditRedaction` detector) drops anything else, and `ProductAnalyticsTests` fail if a prohibited
field survives.

Writes use `attribute_not_exists(idempotency_key)` so retries never double-count. The table has
point-in-time recovery for a consistent reporting snapshot and no TTL (funnel history is retained).
Analytics is opt-out via `HUMBUGG_ANALYTICS_ENABLED`. Reads are internal only — Logs Insights over
the emitter's structured `analytics_event` lines, or a DynamoDB export to S3 + Athena. The full
event catalogue, metric formulas, and reporting queries are in
[`docs/analytics.md`](../docs/analytics.md).

## SES domain authentication

The `email` module repairs or creates the `humbugg.com` SES domain identity in
us-east-1 using the idempotent SES verification APIs. Terraform owns:

- the `_amazonses` identity-verification TXT record;
- three Easy DKIM CNAME records;
- `mail.humbugg.com` as the custom MAIL FROM domain, with SES MX and SPF;
- `_dmarc.humbugg.com` with an initial monitoring policy (`p=none`) and relaxed
  DKIM/SPF alignment suitable for the MAIL FROM subdomain.

Production transactional mail uses `no-reply@humbugg.com`. The deploy workflow
waits for identity, DKIM, and MAIL FROM status to reach `SUCCESS`, then exercises
delivery, bounce, and complaint feedback with SES mailbox-simulator addresses.
It never sends a test message to a real recipient. Tighten DMARC only after
deliverability monitoring is in place.

The backend Lambda has no direct SES, S3, SQS-send, or SMTP permissions. The
shared Mailer platform grants it `execute-api:Invoke` only for Humbugg's message
and attachment-registration routes. A separate least-privilege status Lambda
consumes Humbugg's Mailer status queue and updates
`humbugg-prod-email-messages`. The table records normalized state and expires records
after 90 days.

AWS names Cognito's custom-SES mode `DEVELOPER`; it is unrelated to Humbugg's
development environment. The production Cognito pool uses that mode to send
signup and recovery messages from the Humbugg SES identity. Those messages
bypass the Mailer API, while the SES authentication configuration set sends
their delivery feedback through Mailer. Per-machine development Cognito pools
retain AWS's managed `COGNITO_DEFAULT` sender.
