# Claude Instructions – storybook

## What this service does

Storybook is an AI portrait studio at `storybook.andreas.services`:

1. Authenticated users upload training photos and group them into projects.
2. A background worker (SQS-triggered Lambda) normalizes images and orchestrates per-project Replicate model fine-tunes.
3. Once a fine-tune finishes, the user can run inference through the same API to generate new portraits.

## Stack

| Layer | Choice |
|---|---|
| Backend API | Flask (Python 3.11) packaged as a Docker container Lambda behind API Gateway |
| Image worker | Second Docker container Lambda, triggered by SQS |
| Frontend | Vite + React + HeroUI (Tailwind) SPA on S3 + CloudFront |
| Auth | AWS Cognito (User Pool + App Client) |
| Data | DynamoDB — many `storybook-*` tables (see backend env vars) |
| Images | S3 (backend bucket) |
| ML | Replicate (fine-tune + inference) plus OpenAI / Stability fallbacks |
| Infra | Terraform in `storybook/infra/` (envs/prod) |

## Directory Structure

```
storybook/
├── backend/                     # Flask + Dockerfile, shipped as container Lambda
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── poetry.lock
│   ├── storybook_core/             # routes → services → repositories, plus clients/models/config
│   └── assets/                  # Prompts, styles, reference assets shipped with the image
├── frontend/
│   └── storybook-ui/            # Vite + React + HeroUI + Tailwind SPA
│       ├── index.html
│       ├── vite.config.ts
│       ├── tsconfig.json        # strict mode
│       └── src/
├── infra/
│   ├── envs/prod/               # Prod Terraform root (state in S3)
│   └── modules/                 # Lambda, Cognito, CloudFront, SQS, DynamoDB, etc.
├── dev-docs/                    # SQS debugging, CloudWatch tailing guides
└── CLAUDE.md                    # ← this file
```

## Shared Infrastructure

Terraform looks up (rather than owns) shared resources from `infra/envs/shared`:

- **ACM wildcard certificate** for `*.andreas.services` (us-east-1 for CloudFront)
- **Route53 hosted zone** for `andreas.services`

A single Route53 A-alias record for `storybook.andreas.services` is added by the storybook CloudFront module.

## Local Development

```bash
# Backend (writes to DynamoDB Local on :8001)
cd storybook/backend
poetry install
docker compose up dynamodb
python -m storybook_core.handlers.local.api.api_dev_server

# Image worker (SQS poller loop against the real prod queue URL)
python -m storybook_core.handlers.local.jobs.poll_image_normalization_handler

# Frontend
cd storybook/frontend/storybook-ui
npm install --legacy-peer-deps
npm run dev
```

The local API server creates the `storybook-*` tables in DynamoDB Local on
startup. Unit tests should keep mocking AWS integrations. Copy
`backend/.env.example → backend/.env` and
`frontend/storybook-ui/.env.local.example → .env.local` for non-DynamoDB values.

## Environment Variables (Prod)

All secrets live in the `storybook-production` GitHub Actions environment. The `deploy-infra` job writes Terraform outputs to SSM under `/storybook/prod/*`, and the `deploy-backend` + `deploy-frontend` jobs read them at deploy time.

Key SSM params:

| Param | Purpose |
|---|---|
| `/storybook/prod/api-url` | API Gateway invoke URL |
| `/storybook/prod/app-url` | Public app URL (CloudFront) |
| `/storybook/prod/lambda-name` | API Lambda function name |
| `/storybook/prod/image-worker-lambda` | Image worker Lambda function name |
| `/storybook/prod/ecr-url` | API ECR repo URL |
| `/storybook/prod/image-worker-ecr-url` | Image worker ECR repo URL |
| `/storybook/prod/s3-frontend-bucket` | Frontend S3 bucket |
| `/storybook/prod/s3-backend-bucket` | Backend image S3 bucket |
| `/storybook/prod/cf-dist-id` | CloudFront distribution ID |
| `/storybook/prod/image-queue-url` | SQS queue URL for the image worker |
| `/storybook/prod/cognito-user-pool-id` | Cognito pool ID |
| `/storybook/prod/cognito-client-id` | Cognito app-client ID |
| `/storybook/prod/cognito-domain` | Cognito hosted domain |

API-key secrets (`OPENAI_API_KEY`, `STABILITY_API_KEY`, `REPLICATE_API_TOKEN`) are set as GitHub secrets on the `storybook-production` environment and injected into the Lambdas at deploy time — never stored in SSM.

## GitHub Workflows

| Workflow | Trigger | What it does |
|---|---|---|
| `.github/workflows/storybook-pr.yml` | PR touching `storybook/**` | Verify backend Docker build, lint + build frontend. No push, no AWS writes. |
| `.github/workflows/storybook-prod.yaml` | Push to `main` touching `storybook/**`, or `workflow_dispatch`, or `workflow_run` after shared infra applies | Single combined deploy. `detect-changes` → `deploy-infra` (terraform apply, writes `/storybook/prod/*` SSM from `storybook/infra/envs/prod`) → `deploy-backend` (updates api + image-worker Lambdas) + `deploy-frontend` (S3 + CloudFront) in parallel. Gated by `storybook-prod` environment. |

### Combined deploy workflow (`storybook-prod.yaml`)

**DAG**

```
detect-changes ─► deploy-infra (if storybook/infra/** changed)
                       │
                       ├─► deploy-backend  (api + image-worker Lambdas)
                       └─► deploy-frontend
```

Both app jobs use `needs: [detect-changes, deploy-infra]` and run when their paths changed OR when `deploy-infra` produced fresh SSM values. App-only changes skip `deploy-infra`; skipped ≠ failure so app jobs still run.

`deploy-backend` builds a single Docker image and tags/pushes it to both the api ECR repo and the image-worker ECR repo, then updates the two corresponding Lambda functions. Both must remain in the same job so the image-worker always stays in sync with the api.

**`workflow_dispatch` inputs**

- `run_infra` (default `true`) — run the `deploy-infra` job.
- `run_app` (default `true`) — run `deploy-backend` and `deploy-frontend`.

**Concurrency**

Group `storybook-prod` with `cancel-in-progress: false` — queued pushes wait for the previous run instead of racing on `update-function-code` across the two Lambdas.

## DynamoDB Tables

The backend reads table names from env vars (`STORYBOOK_*_TABLE`) wired up by the deploy workflow:

- `storybook-prod-user-profiles`, `storybook-prod-child-profiles`
- `storybook-prod-story-projects`, `storybook-prod-story-pages`, `storybook-prod-story-states`
- `storybook-prod-chat-messages`
- `storybook-prod-character-assets`, `storybook-prod-images`
- `storybook-prod-model-projects`, `storybook-prod-generation-history`, `storybook-prod-training-runs`

All accessed via boto3 directly from the Lambdas.
Local app runs use DynamoDB Local via `DYNAMODB_ENDPOINT_URL=http://localhost:8001`;
production leaves that unset and uses AWS DynamoDB.
`storybook_core.repositories.dynamodb` owns boto3/local table bootstrap; repository modules
own Storybook persistence operations.
