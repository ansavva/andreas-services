# Claude Instructions – humbugg

## What this service does

Humbugg is a gift-exchange platform served at `humbugg.andreas.services`:

1. Organizers create a group, invite members, and each member fills in a wish list / "do-not-give" list.
2. A matching engine assigns each member a recipient (Secret Santa-style) while respecting exclusions.
3. Members sign in via AWS Cognito and see their assignment in the React SPA.

## Stack

| Layer | Choice |
|---|---|
| Backend | Flask (Python) packaged as a Docker container Lambda behind API Gateway HTTP API |
| Frontend | Vite + React + Tailwind SPA on S3 + CloudFront |
| Auth | AWS Cognito (User Pool + App Client); backend validates JWTs, SPA uses password-grant via `/oauth2/token` |
| Data | DynamoDB — tables `humbugg-profiles`, `humbugg-groups`, `humbugg-groupmembers` |
| Infra | CloudFormation in `humbugg/infra/` |

## Directory Structure

```
humbugg/
├── backend/                    # Flask app + Dockerfile, shipped as container Lambda
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/                    # routes → controllers → services → repositories
├── frontend/                   # Vite + React SPA
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   └── src/
├── infra/
│   ├── backend-lambda.yaml     # Lambda container + API Gateway + Cognito references
│   ├── frontend-cloudfront.yaml # S3 + CloudFront + Route53 alias
│   └── deploy.sh               # Manual local deploy (CI-equivalent)
└── CLAUDE.md                   # ← this file
```

## Shared Infrastructure

The CloudFormation templates reference (but don't own) two shared resources from `terraform/envs/shared`:

- **ACM wildcard certificate** (`*.andreas.services`) — looked up at deploy time via `aws acm list-certificates`
- **Route53 hosted zone** (`andreas.services`) — looked up at deploy time via `aws route53 list-hosted-zones`

The frontend stack adds a single Route53 A-alias record for `humbugg.andreas.services` pointing at its CloudFront distribution.

## Local Development

```bash
# Backend
cd humbugg/backend
pip install -r requirements.txt
python src/app.py   # http://localhost:5000

# Frontend (separate terminal)
cd humbugg/frontend
npm install --legacy-peer-deps
npm run dev         # http://localhost:5173
```

The frontend expects these Vite env vars (create `frontend/.env.local`):

```
VITE_API_URL=http://localhost:5000
VITE_COGNITO_USER_POOL_ID=us-east-1_xxx
VITE_COGNITO_CLIENT_ID=xxx
VITE_AWS_REGION=us-east-1
```

## Environment Variables (Prod)

All secrets/values live in the `humbugg-production` GitHub Actions environment. The infra workflow writes the resolved values into SSM Parameter Store under `/humbugg/prod/*`, and the app workflow reads them at deploy time.

| SSM param | Purpose |
|---|---|
| `/humbugg/prod/api-url` | API Gateway invoke URL |
| `/humbugg/prod/lambda-name` | Backend Lambda function name |
| `/humbugg/prod/ecr-url` | Backend ECR repo URL |
| `/humbugg/prod/cognito-user-pool-id` | Cognito pool ID |
| `/humbugg/prod/cognito-client-id` | Cognito app-client ID |
| `/humbugg/prod/s3-bucket` | Frontend S3 bucket |
| `/humbugg/prod/cf-dist-id` | CloudFront distribution ID |

## GitHub Workflows

| Workflow | Trigger | What it does |
|---|---|---|
| `.github/workflows/humbugg-validate-pr.yml` | PR touching `humbugg/**` | Build backend Docker image (verify only), build frontend, no push |
| `.github/workflows/humbugg-deploy-app-prod.yml` | Push to `main` touching `humbugg/backend/**` or `humbugg/frontend/**` | Build + push backend image to ECR, update Lambda code + env; build frontend, sync to S3, invalidate CloudFront. Gated by `humbugg-production` environment. |
| `.github/workflows/humbugg-deploy-infra-prod.yml` | Push to `main` touching `humbugg/infra/**` | Deploy backend-lambda + frontend-cloudfront CloudFormation stacks; write outputs into `/humbugg/prod/*` SSM params. Gated by `humbugg-production` environment. |

## DynamoDB Tables

- `humbugg-profiles` — per-user profile and wish-list data
- `humbugg-groups` — group metadata (owner, name, member list)
- `humbugg-groupmembers` — group ↔ member relationship + assignment results

All accessed via boto3 directly from the Lambda (no ORM, no VPC).
