# Humbugg email operations

Humbugg submits product email to the shared Mailer API. Mailer owns SES
delivery, suppression, the product-email kill switch, feedback normalization,
and the send and status DLQs. See
[`mailer/docs/operations.md`](../../mailer/docs/operations.md) for platform
recovery.

## Essential vs non-essential email (opt-out)

Each account has a `non_essential_emails_enabled` preference (default **on**),
stored on the `humbugg-profiles` row, editable from **Settings → Email
notifications**, and exposed on `GET`/`PUT /api/me`. It governs whether Humbugg
sends that account **non-essential** product email.

The single source of truth for what counts as essential is
`EmailClassification` in
`backend/Humbugg.Api/Services/Email/Core/EmailClassification.cs`. Change that
switch — nowhere else — to reclassify a category.

| Category (`EmailCategory`) | Importance | Governed by the toggle? |
|---|---|---|
| `Invitation` ("you've been invited") | Essential (join-critical) | No — always sends |
| `DrawCompleted` ("your assignment is ready") | Essential (join-critical) | No — always sends |
| `AssignmentAvailable` ("your assignment is ready") | Essential (join-critical) | No — always sends |
| `Reminder` | Non-essential | Yes |
| `AccountExchangeEvent` (group-activity / question-and-reply) | Non-essential | Yes |

Cognito security/account mail (sign-up, resend-confirmation, forgot-password)
originates in Cognito, never passes through this service, and is always
essential.

Enforcement is a single choke point: `TransactionalEmailService.SendAsync`
consults `IEmailPreferenceGate` before reserving a delivery slot. The production
gate (`AccountEmailPreferenceGate`) resolves the recipient's preference from
their profile by the account id carried on the message
(`TransactionalEmail.RecipientUserId`):

- **Essential** categories are always allowed — the gate never reads the
  preference.
- **Non-essential** categories are **suppressed** when the recipient has opted
  out. Suppression returns a normal `EmailSendResult` with `Suppressed = true`
  (no exception, no ledger reservation, no transport call), so batch and
  reminder jobs keep iterating over the rest of their recipients cleanly.
- A non-essential message whose recipient cannot be tied to an account
  (`RecipientUserId` is null, or no profile exists) **fails open** (sends) so a
  missing account never silently drops mail. Only an explicit opt-out
  suppresses.

Opted-out users still see the same activity in-app; the toggle silences email
delivery only, so nothing that matters is lost — it is just not emailed.

## Humbugg status consumer

`humbugg-email-status-production` consumes only
`mailer-production-humbugg-status` and updates only
`humbugg-email-messages`. The handler accepts version 1 status events for the
`humbugg` service, ignores duplicate or stale events, and returns failed SQS
records for retry. Records contain identifiers, category, normalized status,
provider message ID, timestamps, and a 90-day TTL. They never contain an email
address, subject, body, filename, or provider diagnostic.

Investigate the `humbugg-email-status-errors-production` alarm together with
the Mailer status-queue age and DLQ alarms. After fixing the handler or its
permissions, redrive the Mailer Humbugg status DLQ to its source queue. The
handler's ordering and event-ID conditions make redrive safe.

## Cognito

AWS calls its custom-SES mode `DEVELOPER`; the name does not refer to Humbugg's
development environment. The `humbugg-production` Cognito pool uses that mode
so Cognito sends signup and recovery messages from `no-reply@humbugg.com`
through this AWS account's SES identity. These messages still originate in
Cognito and do not pass through the Mailer API or its send queue.

The SES authentication configuration set copies delivery, bounce, and complaint
events into Mailer's feedback processing. Humbugg stores that normalized
feedback under `auth_<SES message ID>`. The `humbugg-development` pool remains
on `COGNITO_DEFAULT`; local signup and recovery codes go to the real address
entered and do not appear in Mailpit.

After a production Cognito change, verify signup, resend-confirmation, and
forgot-password email. Do not complete this check with a real user address
unless its owner has agreed to receive the messages.

## Deployment verification

The production workflow sends to the SES success, bounce, and complaint mailbox
simulators through the authentication configuration set. It waits for
`delivery`, `bounce`, and `complaint` records in `humbugg-email-messages`.
Simulator mail does not go to a real recipient.

Product sends can be stopped without disabling authentication mail by setting:

```text
/mailer/prod/humbugg/exchange-email-enabled = false
```
