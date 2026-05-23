# Claude Instructions – scout

## What this service does

Scout event listings from Gmail subscriptions and displays them at `scout.andreas.services/app`:

1. **EventBridge** triggers `email-processor` Lambda every Monday at 08:00 UTC
2. Lambda fetches emails with the **"Events"** Gmail label, extracts structured event data via Claude (claude-haiku-4-5), stores results in DynamoDB
3. **events-api** Lambda serves a REST API via API Gateway
4. Vite + React + TypeScript SPA (S3 + CloudFront) displays events

### Regions, categories & the approval workflow

Events are governed by three concepts surfaced through an **admin console** (behind Cognito login):

- **Approval** — extracted events start as `status="pending"` and are invisible to the public until an admin approves (publishes) them; an admin can also reject, edit (any field, any state), or unpublish.
- **Region** (`where`) — derived from a **sender → region(s) mapping** (`scout-senders`). A sender may map to several regions. Unknown senders are recorded as `pending` and their events stay hidden (region-less) until classified; classifying re-tags the sender's existing events.
- **Category** (`what`) — Claude tags each event from a controlled vocabulary (`scout-categories`, active rows) and may propose new ones, which land as `suggested` for the admin to approve/reject.

A published event is public iff `status=published` **and** it has region(s). End users browse by region (URL path `/:region` + dropdown) and filter by category (chips). Region/category lists are discovered dynamically from event data.

## Directory Structure

```
scout/
├── infra/                       # Terraform (CloudFormation is NOT used)
│   ├── modules/                 # auth, api_domain, api_gateway, compute, hosting, storage
│   └── envs/                    # prod, pr (per-PR ephemeral), pr-preview (shared)
├── setup-frontend.sh            # Frontend local dev bootstrap
├── .env.example                 # Required env var template (copy to .env for local use)
├── backend/
│   ├── email-processor/
│   │   ├── Dockerfile           # ECR image — public.ecr.aws/lambda/python:3.11 base
│   │   ├── lambda_function.py   # Gmail → Claude → DynamoDB
│   │   ├── taxonomy.py          # sender normalization + slug helpers
│   │   ├── pyproject.toml
│   │   └── poetry.lock
│   ├── events-api/
│   │   ├── Dockerfile           # ECR image — public.ecr.aws/lambda/python:3.11 base
│   │   ├── lambda_function.py   # public read API + /api/admin/* console API
│   │   ├── taxonomy.py          # copy of the email-processor helper (separate image)
│   │   ├── pyproject.toml
│   │   └── poetry.lock
│   └── migrations/              # one-off backfill scripts (populate_emails_table, backfill_taxonomy)
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

Terraform references (but does not own) two shared resources via `data` sources:

- **ACM wildcard certificate** (`*.andreas.services`, us-east-1) — `data "aws_acm_certificate"`
- **Route53 hosted zone** (`andreas.services`) — `data "aws_route53_zone"`

Scout's Terraform adds Route53 A-alias records for `scout.andreas.services` (CloudFront) and `scout-api.andreas.services` (API Gateway). It does **not** manage the zone or certificate.

## Environment Variables

All secrets live in the `scout-production` GitHub Actions environment, never in committed files.

| Variable | Where set | Description |
|----------|-----------|-------------|
| `ANTHROPIC_API_KEY` | GitHub secret | Anthropic API key |
| `GMAIL_CLIENT_ID` | GitHub secret | Google OAuth client ID |
| `GMAIL_CLIENT_SECRET` | GitHub secret | Google OAuth client secret |
| `GMAIL_REFRESH_TOKEN` | GitHub secret | OAuth refresh token (Lambda mints access tokens from this on each cold start) |
| `VITE_API_URL` | GitHub var | API Gateway endpoint URL |
| `VITE_COGNITO_USER_POOL_ID` | GitHub var | Cognito user pool ID for the admin login (Terraform output `cognito_user_pool_id`) |
| `VITE_COGNITO_CLIENT_ID` | GitHub var | Cognito app client ID for the admin login (Terraform output `cognito_user_pool_client_id`) |
| `S3_BUCKET_NAME` | GitHub var | Website S3 bucket name |
| `CLOUDFRONT_DISTRIBUTION_ID` | GitHub var | CloudFront distribution ID |
| `AWS_ROLE_ARN` | GitHub secret | OIDC IAM role for GitHub Actions |

Admin users are created with `aws cognito-idp admin-create-user` (no public self-signup).

For local use: `cp .env.example .env` and fill in values.

## Lambda Functions

### email-processor

- **Trigger**: EventBridge `cron(0 8 ? * MON *)` — weekly
- **Runtime**: Python 3.11, 256 MB, 300 s timeout
- Authenticates Gmail via OAuth — mints a fresh access token from the stored refresh token on each cold start. The OAuth consent screen **must** be in "In production" status; Testing-mode refresh tokens expire after 7 days.
- Skips emails already in DynamoDB (dedup by Gmail `email_id`)
- Converts HTML bodies to plain text via `html2text` before sending to Claude
- Claude (claude-haiku-4-5) returns a JSON array — one object per event in the email — tagged with categories from the active vocabulary, plus any `new_categories` proposals
- Resolves the sender's region(s) (creating a pending classification for unknown senders) and stamps `status=pending`, `regions`, `categories`, `sender_key` on each event

### events-api

- **Trigger**: API Gateway
- **Runtime**: Python 3.11, 128 MB, 30 s timeout
- Public (no auth): `GET /api/events` (`?upcoming` `?region` `?category`, published only), `GET /api/events/{id}`, `GET /api/regions`, `GET /api/categories`
- Admin (Cognito authorizer on `/api/admin/{proxy+}`): `GET/POST/PUT/DELETE /api/admin/events|senders|categories|emails` — approval queue, sender classification (+re-tag), category review
- `OPTIONS /*` — CORS preflight

Routing anchors on the `/api/` path segment, so the one Lambda serves explicit
resources, the `{proxy+}` catch-all, and any custom-domain base path.

Routes live under `/api/...` so the same Lambda code serves both prod
(`scout-api.andreas.services/api/events`) and PR previews
(`scout-api-pr.andreas.services/<N>/api/events`). In both cases the API
Gateway base path mapping strips everything before `/api` before the Lambda
sees the request.

## DynamoDB Schema

Email metadata lives in `scout-emails`, not on the event records (they were split
out — there is no `created_at` field). All tables are `PAY_PER_REQUEST` + SSE, and
PR previews suffix every table name with `-pr-<N>`.

**`scout-events`** · PK `event_id` (UUID)

| Field | Type | Notes |
|-------|------|-------|
| `event_id` | String | UUID primary key |
| `email_id` | String | Source email (Gmail message ID); join key to `scout-emails` |
| `event_name` / `date` / `time` / `venue` / `price` / `description` | String | `date` is YYYY-MM-DD or empty |
| `links` | List[String] | URLs extracted from the email |
| `status` | String | `pending` \| `published` \| `rejected` — public API serves only `published` |
| `regions` | List[String] | region slugs (empty ⇒ hidden until the sender is classified) |
| `categories` | List[String] | category slugs (may include not-yet-approved ones) |
| `sender_key` | String | normalized sender; join key for re-tagging on classification |
| `reviewed_at` / `reviewed_by` | String | set on approve/reject |

**`scout-emails`** · PK `email_id` — `email_subject`, `email_sender`, `sender_key`, `regions`, `source_email_date`, `image_url`, `processed_at`, `event_count`

**`scout-senders`** · PK `sender_key` — `display_sender`, `regions` (List), `status` (`pending`\|`classified`), `first_seen`, `updated_at`

**`scout-regions`** · PK `slug` — `name`, `created_at`

**`scout-categories`** · PK `slug` — `name`, `status` (`active`\|`suggested`), `created_at`, `suggested_count`

## Deployment

**Automated (preferred):** Push to `main` — GitHub Actions runs the combined `.github/workflows/scout-prod.yaml` workflow. Per the monorepo convention the jobs are `detect-changes → build-and-push → deploy-infra → update-lambda + deploy-frontend` (Terraform `apply` on `scout/infra/envs/prod`). The image build runs before Terraform because Lambdas reference `${ecr_repo}:latest` with `lifecycle { ignore_changes = [image_uri, environment] }`.

- `scout/infra/**` → `deploy-infra` runs, then fans out to both app jobs
- `scout/backend/**` → image build + `update-lambda` only
- `scout/frontend/**` → `deploy-frontend` only

### Combined deploy workflow (`scout-prod.yaml`)

**DAG**

```
detect-changes ─► build-and-push ─► deploy-infra (terraform apply, if scout/infra/** changed)
                                          │
                                          ├─► update-lambda   (set env vars, pin image to :${sha})
                                          └─► deploy-frontend  (Vite build → S3 + CloudFront)
```

**`workflow_dispatch` inputs**

- `run_infra` (default `true`) — run `deploy-infra`.
- `run_app` (default `true`) — run `update-lambda` and `deploy-frontend`.

**Concurrency**

Group `scout-prod` with `cancel-in-progress: false` — queued pushes wait for the previous run instead of racing on `update-function-code`.

## Local Frontend Development

```bash
./setup-frontend.sh https://scout-api.andreas.services/api   # or any /api-suffixed URL
cd frontend && npm run dev
```

`setup-frontend.sh` writes `frontend/.env.local` with `VITE_API_URL` and
`VITE_BASE=/app/`.

## PR Previews

Every `pull_request` (opened / synchronize / reopened) whose diff touches
`scout/**` runs `.github/workflows/scout-pr.yml`. The workflow validates
first (`lint-unit-build`: Python unit tests + frontend lint + frontend build);
only if that job succeeds does `deploy-preview-infra` reapply the shared
PR-preview stack, and only then does `deploy-preview` spin up the per-PR
ephemeral environment:

| | Prod | PR `<N>` |
|---|---|---|
| Frontend | `scout.andreas.services/app` | `scout-pr.andreas.services/<N>/app` |
| API      | `scout-api.andreas.services/api` | `scout-api-pr.andreas.services/<N>/api` |

The shared PR-preview infrastructure (one S3 bucket, one CloudFront
distribution with a CloudFront Function for SPA fallback, and one API Gateway
custom domain) lives in Terraform under `infra/envs/pr-preview`. It is applied
by the `deploy-preview-infra` job inside `scout-pr.yml` itself — every PR
reapplies it (idempotent). The per-PR `deploy-preview` job then applies
`infra/envs/pr` with a `-backend-config` state key of `scout/pr/<N>/terraform.tfstate`.

### DAG

```
lint-unit-build ─► deploy-preview-infra ─► deploy-preview
```

This removes the old "bootstrap on fresh AWS account by running
scout-deploy-preview-infra manually first" step — every PR self-heals the
shared stack, so a brand-new account just needs the first PR to complete.

Per-PR resources live in `infra/envs/pr` (state key `scout/pr/<N>/...`):
Lambda + REST API with `/api/...` routes, DynamoDB tables suffixed
`-pr-<N>`, a fresh Cognito User Pool + Client with the PR's preview URL as
callback, and a base path mapping that attaches the PR's API to the shared
custom domain under `/<N>`.

Closing the PR triggers `.github/workflows/scout-pr-teardown.yaml`, which
`terraform destroy`s the per-PR env, empties the S3 prefix, and invalidates CloudFront.

### Constraints
- REST API Gateway `BasePathMapping` base paths are a **single path segment**
  — that's why the base path is just `<N>` and the `/api/` prefix lives
  inside the API itself.
- Regional API Gateway custom domains require a regional ACM cert; the shared
  `*.andreas.services` wildcard lives in `us-east-1`, which satisfies that.
- The shared GitHub Actions OIDC trust policy (`infra/envs/shared`)
  already allows `repo:<org>/<repo>:*`, so `pull_request` refs can assume
  the CI role without any changes.
