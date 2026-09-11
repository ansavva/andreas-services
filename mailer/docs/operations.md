# Mailer operations

## Health signals

Investigate immediately when a Mailer Lambda error alarm, DLQ alarm, or
15-minute queue-age alarm fires. SES reputation is account-wide, so elevated
bounces or complaints affect every application even though configuration sets
are separated.

## Where alarms go

Every alarm publishes to `mailer-prod-alerts`, one SNS topic with an email
subscription (decision 2026-09-09). Both `alarm_actions` and `ok_actions` are set, so
a recovery mail closes the loop and a quiet inbox means healthy rather than
unmonitored.

| Alarm | Metric | Threshold |
| --- | --- | --- |
| `mailer-prod-{ingress,sender,feedback}-errors` | `AWS/Lambda` `Errors` Sum, 300s | > 0 |
| `mailer-prod-{send,feedback,status}-dlq-not-empty` | `AWS/SQS` `ApproximateNumberOfMessagesVisible` Max, 300s | > 0 |
| `mailer-prod-humbugg-send-oldest-message` | `AWS/SQS` `ApproximateAgeOfOldestMessage` Max, 300s | > 900s |
| `mailer-prod-attachment-threat` | `Mailer` `AttachmentThreat` Sum, 300s | > 0 |
| `mailer-prod-attachment-scan-failure` | `Mailer` `AttachmentScanFailure` Sum, 300s | > 0 |
| `mailer-prod-humbugg-rejects` | `Mailer` `Reject` Sum, 300s | > 0 |
| `mailer-prod-ses-bounce-rate` | `AWS/SES` `Reputation.BounceRate` Avg, 900s | > 0.05 |
| `mailer-prod-ses-complaint-rate` | `AWS/SES` `Reputation.ComplaintRate` Avg, 900s | > 0.001 |

Humbugg's send and status DLQs live in this stack, so Humbugg's own alerting cannot
see them. These alarms are where a stuck Humbugg exchange email surfaces.

The address is `TF_VAR_alert_email`, injected in CI from the GitHub secret
`MAILER_ALERT_EMAIL`. It is `sensitive` and defaults to `""`; the topic is always
created and the subscription only when the address is non-empty, so the stack applies
before the secret exists.

**An SNS email subscription delivers nothing until the recipient clicks the AWS
confirmation link.** Until then it sits in `PendingConfirmation` and every
notification is discarded — Terraform reports it as created either way. Check it:

```bash
aws sns list-subscriptions-by-topic \
  --topic-arn "$(terraform -chdir=infra/envs/prod output -raw alerts_topic_arn)" \
  --query 'Subscriptions[].[Protocol,Endpoint,SubscriptionArn]' --output table
```

A `SubscriptionArn` of `PendingConfirmation` means nobody is being told anything. AWS
expires the link after three days; re-run the deploy to re-send it.

Prove delivery without waiting for a real fault, then put the alarm back:

```bash
aws cloudwatch set-alarm-state --alarm-name mailer-prod-sender-errors \
  --state-value ALARM --state-reason test
aws cloudwatch set-alarm-state --alarm-name mailer-prod-sender-errors \
  --state-value OK --state-reason test
```

## Product-email kill switch

Each application has an SSM parameter. For Humbugg it is:

```text
/mailer/prod/humbugg/exchange-email-enabled
```

Set the value to `false` to stop product sends before SES. Authentication mail
uses a separate Cognito configuration set and is not controlled by this switch.

## DLQ recovery

1. Inspect message identifiers and failure metadata only. Do not paste queue
   bodies or SES payloads into issues because they can contain private content.
2. Fix the underlying permission, validation, provider, or scan failure.
3. Redrive the DLQ into its source queue.
4. Confirm queue age and Lambda errors return to zero.

The sender marks a message `submitting` before calling SES. If a Lambda stops in
the ambiguous call window, it does not automatically send again. Wait for SES
feedback to repair the accepted state. Escalate a long-lived `submitting` record
for manual provider-event review rather than resetting it blindly.

## Suppression removal

Hard bounces and complaints are stored as irreversible recipient hashes and are
also covered by the SES account suppression list. Remove suppression only after
the address owner explicitly requests mail again and the cause is understood.
Both the Mailer table and SES account list must be reviewed.

## Attachments

Only objects tagged `GuardDutyMalwareScanStatus=NO_THREATS_FOUND` are readable by
the sender. Missing tags are pending and retryable. Threats, unsupported files,
access failures, and scan failures are terminally blocked. Quarantined content
expires after 14 days.

## Privacy

CloudWatch logs and DynamoDB records must contain only service IDs, message IDs,
categories, statuses, provider IDs, hashes, and timestamps. Never add recipient,
subject, body, filename, object key, presigned URL, or raw SES-event logging.
