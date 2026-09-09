# alerting

One SNS topic — `humbugg-prod-alerts` — and every production CloudWatch alarm that
publishes to it. Alarms live here rather than beside the resource they watch so that
"what pages someone" is one file, and so no module needs a dependency edge back on
the topic.

## Subscription

`alert_email` is `sensitive` and defaults to `""`. The topic is always created; the
subscription is gated on a non-empty address (`count = var.alert_email != "" ? 1 : 0`),
the pattern `modules/billing` uses for the Stripe parameters — so the stack applies
cleanly before the secret exists. CI passes `TF_VAR_alert_email` from the GitHub
secret `HUMBUGG_ALERT_EMAIL`.

**An email subscription delivers nothing until the recipient confirms it.** AWS mails
a confirmation link; until it is clicked the subscription sits in
`PendingConfirmation` and every alarm notification is discarded. Terraform reports the
subscription as created either way and cannot tell the difference.

## Alarm shape

Every alarm sets **both** `alarm_actions` and `ok_actions`, so a recovery mail closes
the loop and a quiet inbox means healthy rather than unmonitored. Every alarm sets
`treat_missing_data = "notBreaching"`: these metrics are published only when something
happens, so absence is the healthy state.

| Alarm | Metric | Threshold | Period |
| --- | --- | --- | --- |
| `humbugg-prod-api-errors` | `AWS/Lambda` `Errors` Sum | ≥ 3 | 300s |
| `humbugg-prod-api-throttles` | `AWS/Lambda` `Throttles` Sum | ≥ 1 | 300s |
| `humbugg-prod-reminders-errors` | `AWS/Lambda` `Errors` Sum | ≥ 3 | 300s |
| `humbugg-prod-marketing-errors` | `AWS/Lambda` `Errors` Sum | ≥ 3 | 300s |
| `humbugg-prod-email-status-errors` | `AWS/Lambda` `Errors` Sum | ≥ 1 | 300s |
| `humbugg-prod-api-5xx` | `AWS/ApiGateway` `5xx` Sum | ≥ 3 | 300s |
| `humbugg-prod-marketing-5xx` | `AWS/ApiGateway` `5xx` Sum | ≥ 3 | 300s |
| `humbugg-prod-<table>-read-throttles` | `AWS/DynamoDB` `ReadThrottleEvents` Sum | ≥ 1 | 300s |
| `humbugg-prod-<table>-write-throttles` | `AWS/DynamoDB` `WriteThrottleEvents` Sum | ≥ 1 | 300s |

Why 3 for Lambda errors: a container Lambda cold-starting on a fresh image, or one
request losing a race with a DynamoDB retry, produces a lone error that resolves
itself. Three inside one five-minute window is a fault. The `email-status` consumer
keeps its original threshold of 1 — every error there is a delivery status that never
reached the ledger, and its traffic is far too low for one to be noise.

Why 1 for throttles: a throttle has no benign case. The function was asked to run and
could not, so a request was dropped.

HTTP APIs publish the metric as `5xx` with an `ApiId` dimension. `5XXError` is the
REST-API name and matches nothing here.

DynamoDB tables are on-demand, which caps throughput per *partition*, not per table —
a hot partition throttles and the request fails, so these alarms stay.
