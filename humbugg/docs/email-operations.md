# Humbugg email operations

Humbugg submits product email to the shared Mailer API. Mailer owns SES
delivery, suppression, the product-email kill switch, feedback normalization,
and the send and status DLQs. See
[`mailer/docs/operations.md`](../../mailer/docs/operations.md) for platform
recovery.

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

Only `humbugg-production` uses Cognito `DEVELOPER` email with the Humbugg SES
identity and Mailer's authentication configuration set. Authentication
feedback is stored under `auth_<SES message ID>`. `humbugg-development` remains
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
