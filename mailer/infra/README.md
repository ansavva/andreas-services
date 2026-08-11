# Mailer infrastructure

The production environment provisions the IAM-authenticated API, private S3
content store, GuardDuty attachment scanning, internal queues, DynamoDB state,
containerized Lambdas, SES event publishing, status routing, and alarms.

State is stored at `s3://andreas-services-terraform-state/mailer/prod/terraform.tfstate`.

Local plans and read-only inspection use the AWS CLI `default` profile:

```bash
terraform -chdir=envs/prod init
terraform -chdir=envs/prod plan
```
