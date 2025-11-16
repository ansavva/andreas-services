# Xronos Infrastructure

This folder contains deployment assets for running the Xronos API in AWS Lambda behind API Gateway and CloudFront, storing events in Amazon DocumentDB, and serving the React app from S3 + CloudFront. The stack is intended to support both staging and production with path-based routing:

- Production: `https://andreas.services/xronos/api` (API) and `https://andreas.services/xronos/web` (web app)
- Staging: `https://andreas.services/staging/xronos/api` and `https://andreas.services/staging/xronos/web`

## CloudFormation template

`infra/cloudformation/xronos-infra.yaml` provisions:

- DocumentDB cluster and instance inside your private subnets.
- Lambda function (container image) with VPC access and environment variables for connecting to DocumentDB.
- HTTP API Gateway wired to the Lambda handler.
- S3 bucket for the static web app plus CloudFront OAC to keep the bucket private.
- CloudFront distribution with path-based behaviors that route `/…/api/*` to API Gateway and `/…/web/*` to S3.
- IAM role `xronos-<stage>-api-role` granting Lambda VPC access and DocumentDB connectivity.

### Required parameters

| Parameter | Notes |
| --- | --- |
| `StageName` | `staging` or `production`. |
| `BasePath` | `/xronos` or `/staging/xronos` depending on the environment. |
| `DomainName` | Domain the CloudFront distribution should answer for (default `andreas.services`). |
| `CertificateArn` | ACM cert in **us-east-1** covering `andreas.services`. |
| `ApiImageUri` | ECR image URI for the Lambda container (built from `server/Dockerfile.lambda`). |
| `VpcId` | VPC hosting DocumentDB and Lambda. |
| `PrivateSubnetIds` | Comma-separated list of private subnet IDs for Lambda. |
| `DocDbSubnetIds` | Comma-separated list of private subnet IDs for DocumentDB. |
| `DocDbUsername` / `DocDbPassword` | Database credentials used in the Mongo connection string. |
| `WebBucketName` | Optional S3 bucket name override. |

## Deployment helper script

`infra/scripts/deploy-environment.sh` wraps `aws cloudformation deploy` and applies the correct base path per stage. Required environment variables:

- `AWS_REGION`
- `API_IMAGE_URI`
- `CLOUDFRONT_CERT_ARN`
- `VPC_ID`, `PRIVATE_SUBNET_IDS`, `DOCDB_SUBNET_IDS`
- `DOCDB_USERNAME`, `DOCDB_PASSWORD`
- (optional) `WEB_BUCKET_NAME`, `DOMAIN_NAME`

Usage:

```bash
AWS_REGION=us-east-1 \
API_IMAGE_URI=111111111111.dkr.ecr.us-east-1.amazonaws.com/xronos:latest \
VPC_ID=vpc-abc123 PRIVATE_SUBNET_IDS="subnet-1,subnet-2" DOCDB_SUBNET_IDS="subnet-1,subnet-2" \
DOCDB_USERNAME=xronosapp DOCDB_PASSWORD='super-secret' \
CLOUDFRONT_CERT_ARN=arn:aws:acm:us-east-1:111111111111:certificate/abcd \
bash infra/scripts/deploy-environment.sh staging
```

## IAM roles

- **GitHub Actions deployer**: Create an IAM role (for example `AndreasServicesGitHubActions`) that trusts the `token.actions.githubusercontent.com` OIDC provider and attaches permissions for CloudFormation deploys, ECR push/pull, S3 uploads, and CloudFront invalidations. Use this role ARN in the GitHub Actions workflow (`ROLE_TO_ASSUME`). `infra/iam/github-actions-trust.json` and `infra/iam/github-actions-policy.json` capture the trust and permission scaffolding.
- **API execution role**: The template creates `xronos-<stage>-api-role` for the Lambda. It allows VPC access and DocumentDB connectivity. If you prefer tighter scoping, attach a policy that only permits access to the specific DocumentDB cluster and Secrets Manager secret holding the credentials.

## Environment variables

The API reads `MONGODB_URI`, `MONGODB_DB`, and `MONGODB_COLLECTION` (optional) to connect to DocumentDB. The CloudFormation template constructs `MONGODB_URI` using the provided username/password and the cluster endpoint; override in Lambda configuration if you prefer a Secrets Manager reference.

The web build honors `VITE_API_BASE_PATH` and `VITE_APP_BASE_PATH` so assets resolve behind the `/xronos/web` (production) or `/staging/xronos/web` (staging) prefixes.
