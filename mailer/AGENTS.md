# Mailer Service Instructions

## Purpose

`mailer/` is the shared outbound-email platform for andreas-services applications.
It owns admission, attachment storage, SES delivery, suppression, feedback, and
the local Mailpit development experience. Applications own their templates and
message copy.

## Boundaries

- `src/mailer/core` contains environment-independent code only.
- `src/mailer/api` contains the one Flask API used by every HTTP runtime.
- `src/mailer/adapters` contains AWS, in-memory, and Mailpit implementations.
- `src/mailer/entrypoints` composes adapters for Lambda and development.
- `core` cannot depend on the other layers; `api` can depend only on `core`.
- The production API is IAM-authenticated and is the only application ingress.
- S3 object keys and internal SQS messages are implementation details.
- Caller identity, sender, configuration set, and status routing come from the
  registered service, never from the request body.
- Local Mailpit must never relay email externally.
- Message bodies, recipients, subjects, filenames, and upload URLs must not be
  written to logs or DynamoDB status records.

## Stack

- Python 3.11
- Containerized AWS Lambda functions
- API Gateway HTTP API, S3, SQS, DynamoDB, SES, SNS, GuardDuty, SSM
- Terraform under `infra/modules` and `infra/envs`
- pytest and ruff for validation

## Development environment

Run `docker compose up --build` from this directory. The API listens on
`127.0.0.1:8026` and Mailpit on `127.0.0.1:8025`.
