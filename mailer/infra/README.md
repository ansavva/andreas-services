# Mailer infrastructure

The production environment provisions the IAM-authenticated API, private S3
content store, GuardDuty attachment scanning, internal queues, DynamoDB state,
containerized Lambdas, SES event publishing, status routing, and alarms.

State is stored at `s3://andreas-services-terraform-state/mailer/prod/terraform.tfstate`.

```bash
terraform -chdir=envs/prod init
terraform -chdir=envs/prod plan
```

Use the AWS CLI `personal` profile for local plans and read-only inspection:

```bash
AWS_PROFILE=personal terraform -chdir=envs/prod plan
```
