# Support-mail forwarding (`support@humbugg.com`)

Inbound mail sent to `support@humbugg.com` is forwarded to the owner's private
inbox **without publishing that destination**. This path is completely separate
from product email: product/transactional mail still originates from
`no-reply@humbugg.com` through the shared Mailer platform (see
[`email-operations.md`](./email-operations.md)). Only the *inbound* receive-and-
forward flow lives here.

## How it works

```
sender ──▶ MX (humbugg.com) ──▶ SES inbound receipt rule (support@ only)
             │                        │
             │                   1. S3 action  → s3://humbugg-support-inbound-production/inbound/<messageId>
             │                   2. Lambda action (async, invocationType=Event)
             ▼                        │
        spam/virus scan          humbugg-support-production-forwarder (Python 3.11)
                                      │  reads raw MIME from S3, parses safely,
                                      │  builds a NEW message, Reply-To = original sender
                                      ▼
                                 SES SendRawEmail  From: no-reply@humbugg.com
                                      ▼
                                 SUPPORT_FORWARD_TO (private inbox, secret)
```

Terraform: `humbugg/infra/modules/support_forwarding`, wired in
`humbugg/infra/envs/prod`. Lambda source + tests:
`humbugg/support-forwarding/`.

### Why Python (not the C# backend container)

Inbound MIME parsing follows the repo's Lambda-mail convention (scout / mailer
are Python 3.11). The function uses only the standard-library `email` package
plus `boto3` (both provided by the Lambda runtime), so Terraform zips the
`support_forwarder` package directly — no ECR image or CI build step. The C#
backend container and its `HUMBUGG_CONSUMER` host are unchanged.

### Safety behaviours (implemented in `handler.py`)

- **Never relays untrusted headers.** A brand-new `EmailMessage` is built; only
  a sanitised subject (CR/LF stripped, length-clamped), the decoded body, and
  size-bounded attachments are copied. `Reply-To` is set to the parsed original
  sender so the owner can reply directly.
- **Spam / virus.** Dropped when SES `spamVerdict` is `FAIL` or `virusVerdict`
  is `FAIL`/`PROCESSING_FAILED` (`scan_enabled = true` populates the verdicts).
- **Mail loops.** Dropped when the message carries our `X-Humbugg-Forwarded`
  marker, when the envelope sender is empty (`<>` bounce/auto-reply), or when
  the sender/From is one of our own domains.
- **Recipient allow-list.** Forwards only mail whose SES recipients include
  `support@humbugg.com` (defence-in-depth on top of the receipt rule).
- **Size / attachments.** Per-attachment cap (`MAX_ATTACHMENT_BYTES`, 6 MB) and
  total-message cap (`MAX_MESSAGE_BYTES`, 9 MB, under the SES 10 MB limit).
  Oversize attachments are omitted with an explanatory note; if the assembled
  message still exceeds the limit, all attachments are stripped. HTML-only mail
  is attached as `original.html`.
- **Malformed mail** is dropped (not retried).
- **Failures / retries.** Transient S3/SES/secret errors raise; the async Lambda
  retries and, on exhaustion, lands on the DLQ
  (`humbugg-support-production-dlq`). Alarms:
  `humbugg-support-production-forwarder-errors` and
  `humbugg-support-production-dlq-not-empty`.

## The `SUPPORT_FORWARD_TO` secret

The private destination is **never committed**. Wiring:

| Where | Value |
|---|---|
| GitHub environment secret (`humbugg-production`) | `SUPPORT_FORWARD_TO` — the real private inbox address |
| CI → Terraform | exported as `TF_VAR_support_forward_to` for the `deploy-infra` job |
| Terraform variable | `support_forward_to` (`sensitive = true`, default `""`) |
| SSM SecureString | `/humbugg/prod/support-forward-to` (created from the var; `ignore_changes = [value]`) |
| Lambda | env `SUPPORT_FORWARD_TO_PARAM=/humbugg/prod/support-forward-to`; fetched at runtime with `WithDecryption` |

The SSM parameter is created with a placeholder (`TODO-set-via-secret`) when the
variable is empty. Until a real value is supplied the Lambda raises a
`ConfigError`, the message lands on the DLQ, and the DLQ alarm fires — so a
missing secret is loud, never silently dropped.

> **TODO (human):** the real private inbox address is a human-provided secret.
> Set the `SUPPORT_FORWARD_TO` GitHub environment secret (or put the value
> directly into the `/humbugg/prod/support-forward-to` SSM SecureString). Do not
> commit it anywhere.

For local plans you may pass `-var 'support_forward_to=you@example.com'` or
`export TF_VAR_support_forward_to=...`; never write it into `terraform.tfvars`.

## Verifying

1. **DNS/MX** — confirm the apex MX resolves to SES inbound:
   `dig +short MX humbugg.com` should include
   `10 inbound-smtp.us-east-1.amazonaws.com`.
2. **Active rule set** — `aws ses describe-active-receipt-rule-set` should show
   `humbugg-inbound-production` with a rule matching `support@humbugg.com`.
3. **Secret present** —
   `aws ssm get-parameter --name /humbugg/prod/support-forward-to --with-decryption`
   returns the real inbox (not the placeholder).
4. **End-to-end** — from an external address, email `support@humbugg.com`; the
   forwarded copy should arrive in the private inbox, `From: no-reply@humbugg.com`,
   `Reply-To:` the original sender. Do **not** test against the real private
   inbox until its owner has agreed. Unit tests (`humbugg/support-forwarding`,
   `pytest`) never send to any real inbox — SES/S3 are faked and the destination
   is a dummy address.

## Failure handling

- **DLQ has messages / alarm firing** — inspect
  `humbugg-support-production-dlq`. Common causes: missing/empty
  `SUPPORT_FORWARD_TO` secret, SES send throttling, or S3 read errors. Fix the
  cause, then redrive the DLQ to re-invoke the Lambda.
- **Forwarder errors alarm** — check
  `/aws/lambda/humbugg-support-production-forwarder` logs.
- **No mail arriving** — verify MX (step 1), that the receipt rule set is the
  *active* one (only one can be active per account/region), and that the SES
  identity/account is out of the sandbox for inbound in this region.

## Human / console prerequisites

- **SES inbound region & sandbox.** SES email receiving must be available/enabled
  in `us-east-1` for this account. Exiting the SES sandbox (if still in it) and
  enabling receiving is a one-time console/support step.
- **Single active receipt rule set.** Applying this Terraform sets
  `humbugg-inbound-production` as the account's active receipt rule set. Only one
  rule set is active per account per region — confirm nothing else relies on a
  different active set before applying.
