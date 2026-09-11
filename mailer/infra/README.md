# Mailer infrastructure

The production environment provisions the IAM-authenticated API, private S3
content store, GuardDuty attachment scanning, internal queues, DynamoDB state,
containerized Lambdas, SES event publishing, status routing, and alarms.

Alarms notify `mailer-prod-alerts`, one SNS topic with an email subscription gated on
`alert_email` (`sensitive`, default `""`, `TF_VAR_alert_email` from the GitHub secret
`MAILER_ALERT_EMAIL`). The alarm table, the confirm-the-subscription step, and how to
test it are in [`docs/operations.md`](../docs/operations.md).

State is stored at `s3://andreas-services-terraform-state/mailer/prod/terraform.tfstate`.

Local plans and read-only inspection use the AWS CLI `default` profile:

```bash
terraform -chdir=envs/prod init
terraform -chdir=envs/prod plan
```
