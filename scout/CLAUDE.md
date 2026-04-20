# Claude Instructions – scout

## What this service does

Aggregates NYC event listings from Gmail subscriptions and displays them at `scout.andreas.services/app`:

1. **EventBridge** triggers `email-processor` Lambda every Monday at 08:00 UTC
2. Lambda fetches emails with the **"Events"** Gmail label, extracts structured event data via Claude (claude-haiku-4-5), stores results in DynamoDB
3. **events-api** Lambda serves a REST API via API Gateway
4. Vite + React + TypeScript SPA (S3 + CloudFront) displays events

## Directory Structure

```
scout/
├── cloudformation.yaml             # Prod infrastructure (DynamoDB, Lambdas, API GW at scout-api.andreas.services, S3, CloudFront at scout.andreas.services/app, Route53)
├── cloudformation-pr-preview.yaml  # Shared PR preview infra (scout-pr.andreas.services bucket+CDN + scout-api-pr.andreas.services custom domain) — deployed once
├── cloudformation-pr.yaml          # Per-PR stack scout-pr-<N> (Lambda + API GW + DynamoDB-pr-<N> + Cognito pool + BasePathMapping)
├── deploy.sh                       # Local/manual end-to-end deployment script
├── setup-frontend.sh            # Frontend local dev bootstrap
├── .env.example                 # Required env var template (copy to .env for local use)
├── lambda/
│   ├── email-processor/
│   │   ├── lambda_function.py   # Gmail → OpenAI → DynamoDB
│   │   └── requirements.txt
│   └── events-api/
│       └── lambda_function.py   # GET /events, GET /events/{id}
├── frontend/
│   ├── index.html               # Vite entry point
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   ├── .eslintrc.json
│   ├── .prettierrc
│   └── src/
│       ├── main.tsx             # React entry point
│       ├── App.tsx              # Root component
│       ├── index.css            # CSS custom properties for light/dark theme
│       ├── vite-env.d.ts        # VITE_ env var types
│       ├── components/          # Header, EventCard, EventFilters, SkeletonCard
│       ├── context/             # ThemeContext (light/dark mode)
│       ├── hooks/               # useEvents (API fetching)
│       ├── utils/               # formatters (formatDate, isUpcoming, etc.)
│       └── types/               # Event, SortOrder, Theme interfaces
└── docs/
    └── SETUP.md                 # Full deployment walkthrough
```

## Shared Infrastructure

The CloudFormation stack references (but does not own) two shared resources from `terraform/envs/shared`:

- **ACM wildcard certificate** (`*.andreas.services`) — looked up at deploy time via `aws acm list-certificates`
- **Route53 hosted zone** (`andreas.services`) — looked up at deploy time via `aws route53 list-hosted-zones`

The stack adds a single Route53 A-alias record for `scout.andreas.services` pointing to its CloudFront distribution. It does **not** manage the zone or certificate.

## Environment Variables

All secrets live in the `scout-production` GitHub Actions environment, never in committed files.

| Variable | Where set | Description |
|----------|-----------|-------------|
| `ANTHROPIC_API_KEY` | GitHub secret | Anthropic API key |
| `GMAIL_CLIENT_ID` | GitHub secret | Google OAuth client ID |
| `GMAIL_CLIENT_SECRET` | GitHub secret | Google OAuth client secret |
| `GMAIL_ACCESS_TOKEN` | GitHub secret | OAuth access token (auto-refreshed by Lambda) |
| `GMAIL_REFRESH_TOKEN` | GitHub secret | OAuth refresh token |
| `LAMBDA_CODE_BUCKET` | GitHub var | S3 bucket for Lambda zip uploads |
| `VITE_API_URL` | GitHub var | API Gateway endpoint URL |
| `S3_BUCKET_NAME` | GitHub var | Website S3 bucket name |
| `CLOUDFRONT_DISTRIBUTION_ID` | GitHub var | CloudFront distribution ID |
| `AWS_ROLE_ARN` | GitHub secret | OIDC IAM role for GitHub Actions |

For local use: `cp .env.example .env` and fill in values.

## Lambda Functions

### email-processor

- **Trigger**: EventBridge `cron(0 8 ? * MON *)` — weekly
- **Runtime**: Python 3.11, 256 MB, 300 s timeout
- Authenticates Gmail via OAuth (auto-refreshes token using stored refresh token)
- Skips emails already in DynamoDB (dedup by Gmail `email_id`)
- Converts HTML bodies to plain text via `html2text` before sending to OpenAI
- Claude (claude-haiku-4-5) returns a JSON array — one object per event in the email

### events-api

- **Trigger**: API Gateway
- **Runtime**: Python 3.11, 128 MB, 30 s timeout
- `GET /api/events` — list all; `?upcoming=true` filters to date ≥ today
- `GET /api/events/{id}` — fetch single event by `event_id`
- `OPTIONS /*` — CORS preflight

Routes live under `/api/...` so the same Lambda code serves both prod
(`scout-api.andreas.services/api/events`) and PR previews
(`scout-api-pr.andreas.services/<N>/api/events`). In both cases the API
Gateway base path mapping strips everything before `/api` before the Lambda
sees the request.

## DynamoDB Schema

Table: `scout-events` · Primary key: `event_id` (UUID string)

| Field | Type | Notes |
|-------|------|-------|
| `event_id` | String | UUID primary key |
| `email_id` | String | Gmail message ID (used for dedup) |
| `event_name` | String | |
| `date` | String | YYYY-MM-DD or empty |
| `time` | String | e.g. "7:00 PM" or empty |
| `venue` | String | |
| `price` | String | |
| `description` | String | |
| `links` | List[String] | URLs extracted from email |
| `email_subject` | String | |
| `email_sender` | String | |
| `created_at` | String | ISO timestamp |
| `source_email_date` | String | RFC 2822 date from email header |

## Deployment

**Automated (preferred):** Push to `main` — GitHub Actions runs the combined `.github/workflows/scout-deploy-prod.yml` workflow (`detect-changes` → `deploy-infra` → `deploy-backend` + `deploy-frontend`). Paths determine which jobs run:

- `scout/cloudformation.yaml` → `deploy-infra` runs, then fans out to both app jobs (fresh SSM values)
- `scout/lambda/**` → `deploy-backend` only
- `scout/frontend/**` → `deploy-frontend` only

### Combined deploy workflow (`scout-deploy-prod.yml`)

**DAG**

```
detect-changes ─► deploy-infra (if scout/cloudformation.yaml changed)
                       │
                       ├─► deploy-backend  (Lambda zips → update-function-code)
                       └─► deploy-frontend (Vite build → S3 + CloudFront)
```

App jobs use `needs: [detect-changes, deploy-infra]` and an `if:` that fires when their paths changed OR when `deploy-infra` produced new SSM values. Skipped upstream infra doesn't block app-only deploys.

**`workflow_dispatch` inputs**

- `run_infra` (default `true`) — run `deploy-infra`.
- `run_app` (default `true`) — run `deploy-backend` and `deploy-frontend`.

**Concurrency**

Group `scout-prod` with `cancel-in-progress: false` — queued pushes wait for the previous run instead of racing on `update-function-code`.

**Manual (local):**
```bash
cp .env.example .env   # fill in secrets
./deploy.sh            # packages lambdas, deploys CFn, builds + syncs frontend
```

See `docs/SETUP.md` for the full guide including Gmail OAuth setup.

## Local Frontend Development

```bash
./setup-frontend.sh https://scout-api.andreas.services/api   # or any /api-suffixed URL
cd frontend && npm run dev
```

`setup-frontend.sh` writes `frontend/.env.local` with `VITE_API_URL` and
`VITE_BASE=/app/`.

## PR Previews

Every `pull_request` (opened / synchronize / reopened) whose diff touches
`scout/**` spins up an ephemeral environment via
`.github/workflows/scout-deploy-preview-pr.yml`:

| | Prod | PR `<N>` |
|---|---|---|
| Frontend | `scout.andreas.services/app` | `scout-pr.andreas.services/<N>/app` |
| API      | `scout-api.andreas.services/api` | `scout-api-pr.andreas.services/<N>/api` |

The shared PR-preview infrastructure (one S3 bucket, one CloudFront
distribution with a CloudFront Function for SPA fallback, and one API Gateway
custom domain) lives in `cloudformation-pr-preview.yaml` and is deployed
once by `scout-deploy-preview-infra.yml`. Its outputs are published to SSM
under `/scout/pr-preview/*` (s3-bucket, cf-dist-id, api-domain).

### Bootstrapping preview infra

On a fresh AWS account, run `scout-deploy-preview-infra.yml` manually via
`workflow_dispatch` before opening the first PR. The per-PR deploy
(`scout-deploy-preview-pr.yml`) starts with a **readiness-check** step that
calls `aws ssm get-parameter` for each `/scout/pr-preview/*` value; if any
are missing it fails immediately with:

> `scout-deploy-preview-infra.yml has never been deployed; run it first.`

After the shared preview stack exists, every PR touching `scout/**` can
deploy cleanly.

Per-PR resources live in `cloudformation-pr.yaml` (stack `scout-pr-<N>`):
Lambda + REST API with `/api/...` routes, a DynamoDB table suffixed
`-pr-<N>` (DeletionPolicy: Delete), a fresh Cognito User Pool + Client with
the PR's preview URL as callback, and a `BasePathMapping` that attaches the
PR's API to the shared custom domain under `/<N>`.

Closing the PR triggers `.github/workflows/scout-teardown-preview-pr.yml`, which
deletes the stack, empties the S3 prefix, and invalidates CloudFront.

### Constraints
- REST API Gateway `BasePathMapping` base paths are a **single path segment**
  — that's why the base path is just `<N>` and the `/api/` prefix lives
  inside the API itself.
- Regional API Gateway custom domains require a regional ACM cert; the shared
  `*.andreas.services` wildcard lives in `us-east-1`, which satisfies that.
- The shared GitHub Actions OIDC trust policy (`terraform/envs/shared`)
  already allows `repo:<org>/<repo>:*`, so `pull_request` refs can assume
  the CI role without any changes.
