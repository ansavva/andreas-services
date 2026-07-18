# Claude Instructions – humbugg

## What this service does

Humbugg is a gift-exchange platform served at `humbugg.com`:

1. Organizers create a group, invite members, and each member fills in a wish list / "do-not-give" list.
2. A matching engine assigns each member a recipient (Secret Santa-style) while respecting exclusions.
3. Members sign in via AWS Cognito and see their assignment in the React SPA.

## Stack

| Layer | Choice |
|---|---|
| Backend | ASP.NET Core 10 (C# 14) packaged as a Docker container Lambda behind API Gateway HTTP API |
| Frontend | Vite + React + Tailwind SPA on S3 + CloudFront |
| Auth | AWS Cognito (User Pool + secretless App Client); branded SPA screens use SRP through Amplify Auth and the API validates access tokens |
| Data | DynamoDB — profiles, groups, groupmembers, private draws, reveal audit events, and email delivery IDs |
| Infra | Terraform in `humbugg/infra/` (`modules/` + `envs/prod`) |

## Directory Structure

```
humbugg/
├── backend/                    # ASP.NET Core app + Dockerfile, shipped as container Lambda
│   ├── Dockerfile
│   ├── Humbugg.slnx
│   ├── Humbugg.Api/             # controllers → services → DynamoDB repositories
│   └── Humbugg.Api.Tests/       # matching and domain tests
├── frontend/                   # Vite + React SPA
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   └── src/
├── infra/                      # Terraform
│   ├── modules/                # auth, compute, hosting, storage
│   └── envs/prod/              # Lambda + API Gateway + Cognito, S3 + CloudFront + Route53 alias
└── CLAUDE.md                   # ← this file
```

## Shared Infrastructure

Terraform references (but doesn't own) two shared resources via `data` sources:

- **Route53 hosted zones** (`humbugg.com` and `andreas.services`) — Terraform data sources

The frontend stack provisions the service-specific us-east-1 ACM certificate
and points apex, `www`, and the legacy hostname at one CloudFront distribution.
CloudFront permanently redirects non-apex requests to `https://humbugg.com`.

## Local Development

```bash
# One-time toolchain setup (from the repo root): installs .NET SDK 10, Node,
# Terraform, tflint, etc. via Homebrew. Idempotent — safe to re-run.
./scripts/dev-setup.sh && ./humbugg/scripts/dev-setup.sh

# Backend
cd humbugg/backend
dotnet restore Humbugg.slnx
docker compose up --build                                  # http://localhost:5001

# Frontend (separate terminal)
cd humbugg/frontend
# The frontend depends on the private @ansavva/design-system package, so npm
# needs a read:packages token exposed as NODE_AUTH_TOKEN (run from repo root):
#   export GITHUB_PACKAGES_TOKEN=<pat-with-read:packages>
#   eval "$(./scripts/github-packages-auth.sh --export)"
npm install --legacy-peer-deps
npm run dev         # http://localhost:5173
```

See [`scripts/README.md`](../scripts/README.md) for the setup scripts and GitHub Packages auth.

The frontend expects these Vite env vars (create `frontend/.env.local`):

```
VITE_API_URL=http://localhost:5001
VITE_COGNITO_USER_POOL_ID=us-east-1_xxx
VITE_COGNITO_CLIENT_ID=xxx
VITE_AWS_REGION=us-east-1
```

## Environment Variables (Prod)

All secrets/values live in the `humbugg-production` GitHub Actions environment. The `deploy-infra` job writes the resolved values into SSM Parameter Store under `/humbugg/prod/*`, and the `deploy-backend` + `deploy-frontend` jobs read them at deploy time.

| SSM param | Purpose |
|---|---|
| `/humbugg/prod/api-url` | API Gateway invoke URL |
| `/humbugg/prod/lambda-name` | Backend Lambda function name |
| `/humbugg/prod/ecr-url` | Backend ECR repo URL |
| `/humbugg/prod/cognito-user-pool-id` | Cognito pool ID |
| `/humbugg/prod/cognito-client-id` | Cognito app-client ID |
| `/humbugg/prod/s3-bucket` | Frontend S3 bucket |
| `/humbugg/prod/cf-dist-id` | CloudFront distribution ID |
| `/humbugg/prod/email-from-address` | Verified transactional sender (`no-reply@humbugg.com`) |

## GitHub Workflows

| Workflow | Trigger | What it does |
|---|---|---|
| `.github/workflows/humbugg-pr.yml` | PR touching `humbugg/**` | Build backend Docker image (verify only), build frontend, no push |
| `.github/workflows/humbugg-prod.yaml` | Push to `main` touching `humbugg/**`, or `workflow_dispatch`, or `workflow_run` after shared infra applies | Single combined deploy. `detect-changes` → `deploy-infra` (Terraform apply on `humbugg/infra/envs/prod`) → `deploy-backend` + `deploy-frontend` in parallel. Gated by `humbugg-production` environment. |

### Combined deploy workflow (`humbugg-prod.yaml`)

**DAG**

```
detect-changes ─► deploy-infra (if humbugg/infra/** changed)
                       │
                       ├─► deploy-backend  (if humbugg/backend/** changed OR infra ran)
                       └─► deploy-frontend (if humbugg/frontend/** changed OR infra ran)
```

App jobs use `needs: [detect-changes, deploy-infra]` and an `if:` that runs when the app changed OR when `deploy-infra` produced new SSM values. If `deploy-infra` is skipped (app-only change) the app jobs still run because `!cancelled() && needs.deploy-infra.result != 'failure'` is true for skipped upstream jobs.

**`workflow_dispatch` inputs**

- `run_infra` (default `true`) — run the `deploy-infra` job.
- `run_app` (default `true`) — run `deploy-backend` and `deploy-frontend`.

Use `run_infra=true, run_app=false` for infra-only reruns, and `run_infra=false, run_app=true` to redeploy just the app using whatever is already in SSM.

**Concurrency**

Group `humbugg-prod` with `cancel-in-progress: false` — queued pushes wait for the previous run instead of racing on `update-function-code` or SSM writes.

## DynamoDB Tables

- `humbugg-profiles` — per-user profile and wish-list data
- `humbugg-groups` — group metadata (owner, name, member list)
- `humbugg-groupmembers` — group ↔ member relationship + assignment results
- `humbugg-draws` — private giver → recipient maps, separate from ordinary group responses
- `humbugg-audit-events` — standard append-only audit trail for sensitive exchange actions (creation/deletion, participant/exclusion/role/entitlement/reminder changes, draws, resets, reveals); see `infra/README.md`
- `humbugg-email-messages` — stable transactional message IDs and delivery state

Production tables are accessed through the AWS SDK for .NET directly from the
Lambda (no ORM, no VPC). Local app runs use DynamoDB Local on `localhost:8001`
and the unsigned shared Mailer API with Mailpit for product email. Mailpit never
relays externally. Unit tests retain the in-memory capture adapter and ledger.
Production signs Mailer API requests with the backend Lambda role, and a
separate status Lambda consumes normalized delivery feedback. Local end-to-end
testing uses the containers. `DynamoDbBootstrap` owns local-only table
bootstrap; repository classes own Humbugg persistence operations.
