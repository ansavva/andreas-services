# Mailer

Mailer is the shared outbound-email platform for the services in this
repository. Applications submit versioned HTTP requests; Mailer owns durable
admission, private content storage, queueing, SES delivery, attachments,
suppression, and normalized feedback.

## Production flow

1. An application role signs `POST /v1/services/<service>/messages` with AWS
   SigV4.
2. The ingress Lambda verifies that the caller role is registered for the route.
3. Mailer stores an internal manifest in S3 and enqueues a small SQS pointer.
4. The sender Lambda validates the content, suppression state, kill switch, and
   attachment scan results before calling SES.
5. SES events are normalized and sent to the application's status queue.

Attachments use `POST /v1/services/<service>/attachment-uploads` to obtain a
15-minute presigned `PUT`; raw attachment bytes never pass through API Gateway.

## Local flow

```bash
docker compose up --build
```

- Mailer API: <http://127.0.0.1:8026>
- Mailpit inbox: <http://127.0.0.1:8025>

The local API uses the production routes and schemas without SigV4. Product
email is delivered only to Mailpit, which has no outbound relay configured.

Example:

```bash
curl -i http://127.0.0.1:8026/v1/services/humbugg/messages \
  -H 'content-type: application/json' \
  --data @contracts/examples/message.json
```

## Privacy and retention

- Access logs contain method, route, status, latency, and request ID only.
- DynamoDB records contain identifiers, hashes, states, and timestamps—not
  message content.
- Successfully delivered S3 content is deleted promptly.
- Abandoned, failed, and quarantined content expires after 14 days.
- Delivery metadata expires after 90 days; suppressions require explicit
  removal.

See [operations.md](docs/operations.md) for alarms and recovery.
