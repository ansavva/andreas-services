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

Local development uses real, per-machine AWS resources rather than LocalStack
or shared developer resources. `dev-aws-setup.sh` persists a random UUID at
`~/.config/andreas-services/humbugg/machine-id`; that UUID scopes Terraform
state, DynamoDB tables, the private S3 bucket, and the Cognito pool. A developer
may therefore use multiple machines without collisions.

```bash
# One-time toolchain and authentication setup (from the repo root).
# The shared setup includes the Stripe CLI from stripe/stripe-cli/stripe.
./humbugg/scripts/dev-setup.sh
stripe login

# Authenticate npm for the private design system package.
export GITHUB_PACKAGES_TOKEN=<pat-with-read:packages>
eval "$(./scripts/github-packages-auth.sh --export)"
npm --prefix humbugg/frontend install --legacy-peer-deps

# Read-only validation of shared tools, .NET, AWS resources, and env files.
./humbugg/scripts/dev-setup.sh --check

# Start backend, frontend, and Stripe webhook forwarding together.
./humbugg/scripts/dev-up.sh
```

The combined launcher retrieves the current Stripe CLI `whsec_...` signing
secret before the backend starts, stores it only in the ignored `backend/.env`,
and supervises all three processes. It does not generate Stripe API keys;
`HUMBUGG_STRIPE_MODE=test`, the test publishable key, and the test secret key
must already be configured according to `docs/stripe-setup.md`. Ctrl+C stops
the complete session. Mailer and Mailpit remain a separate shared dependency
and should be started with `cd mailer && docker compose up --build`.

### Development scripts

All commands run from the repository root:

| Script | Agent/developer usage |
|---|---|
| `scripts/dev-setup.sh` | Idempotently install shared tooling; use `--check` for a read-only prerequisite audit |
| `humbugg/scripts/dev-setup.sh` | Canonical dependency chain: shared setup → .NET 10 → per-machine AWS setup; accepts `--profile`, `--region`, `--yes`, `--check` |
| `humbugg/scripts/dev-aws-setup.sh` | Lower-level AWS provision/check command called by canonical setup; accepts `--profile`, `--region`, `--yes`, `--check` |
| `humbugg/scripts/dev-up.sh` | Preferred full local startup; accepts `--profile`, `--region`, `--forward-to` |
| `humbugg/scripts/dev-up-backend.sh` | Backend-only startup; exports temporary AWS credentials into Docker Compose without writing them to disk |
| `humbugg/scripts/dev-up-frontend.sh` | Frontend-only startup; validates `.env.local` and installed dependencies first |
| `humbugg/scripts/dev-up-stripe.sh` | Stripe-only listener for the billing webhook's exact event allowlist; copy its `whsec_...` value into `backend/.env` and restart the backend when running components separately |
| `humbugg/scripts/dev-logs-backend.sh` | Follow the backend container logs; accepts Docker Compose log options such as `--tail 200` |
| `humbugg/scripts/dev-aws-reset.sh` | Destructive data reset scoped to this machine; run with `--dry-run` first; `--skip-cognito` preserves users |
| `humbugg/scripts/dev-aws-destroy.sh` | Destroy this machine's AWS resources; the persistent UUID is deliberately retained |

`humbugg/scripts/dev-aws-common.sh` is a sourced implementation helper, not a
user command. AWS commands default to `$AWS_PROFILE`/`default` and
`$AWS_REGION`/`$AWS_DEFAULT_REGION`/`us-east-1`; the `default` profile is the
right one for this repo, so `--profile` is only needed to override it.

To start components separately:

```bash
./humbugg/scripts/dev-up-backend.sh                     # http://localhost:5001
./humbugg/scripts/dev-up-frontend.sh                    # http://localhost:5173
./humbugg/scripts/dev-up-stripe.sh                      # forwards billing webhooks
./humbugg/scripts/dev-logs-backend.sh                   # follows backend logs
```

To reset or remove only the current machine's environment:

```bash
./humbugg/scripts/dev-aws-reset.sh --dry-run
./humbugg/scripts/dev-aws-reset.sh
./humbugg/scripts/dev-aws-destroy.sh
```

The reset script verifies the Terraform machine UUID and exact AWS resource
prefix before deleting data. It recreates the DynamoDB tables through Terraform,
empties S3, and deletes Cognito users unless `--skip-cognito` is supplied. It
retains the pool and app client. The destroy script removes all per-machine AWS
resources but retains the UUID and state identity for safe reprovisioning.

See [`scripts/README.md`](../scripts/README.md) for the setup scripts and GitHub Packages auth.

`dev-aws-setup.sh` generates these frontend values in the ignored
`frontend/.env.local` file; do not create shared or committed values manually:

```
VITE_COGNITO_USER_POOL_ID=<generated by scripts/dev-aws-setup.sh>
VITE_COGNITO_CLIENT_ID=<generated by scripts/dev-aws-setup.sh>
VITE_AWS_REGION=us-east-1
VITE_APP_BASE_URL=http://localhost:5173
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
| `/humbugg/prod/email-from-address` | Verified transactional sender (`no-reply@humbugg.com`). Outbound app mail is SES via the shared Mailer; **inbound** mail (e.g. `support@humbugg.com`) is Google Workspace — see `docs/support-email.md` |
| _(env var, not SSM)_ `HUMBUGG_APP_BUCKET` | Shared application object bucket (`humbugg-app-production`, in the `storage` module); set literally in `update-lambda`. Profile photos live under the `avatars/` prefix — private, written by the Lambda under `avatars/*` (least-privilege IAM) and served read-only at `/avatars/*` through the app CloudFront distribution via OAC. Local development uses the per-machine AWS bucket created by `scripts/dev-aws-setup.sh`. Avatar URLs derive from `APP_BASE_URL` unless `HUMBUGG_AVATAR_BASE_URL` overrides it. |
| `/humbugg/prod/stripe/publishable-key` | Stripe **test-mode** publishable key (`String`; Terraform `billing` module) |
| `/humbugg/prod/stripe/secret-key` | Stripe **test-mode** secret key (`SecureString`; Terraform `billing` module) |
| `/humbugg/prod/stripe/webhook-secret` | Stripe webhook signing secret (`SecureString`; Terraform `billing` module) |

### Stripe billing (test mode only)

Billing config is **environment/SSM-sourced, never hardcoded**. Product/price IDs
flow through GitHub env `vars.*` into Lambda env; the secret key and webhook secret
are GitHub env `secrets.*`, injected via `TF_VAR_*` into the `billing` Terraform
module (which stores them as SSM `SecureString`) and set as Lambda env vars in
`update-lambda`. `StripeSettings.FromEnvironment()` validates at startup: it fails
fast when `HUMBUGG_STRIPE_MODE=test` without the required test-mode credentials, and
**blocks live mode** (`HUMBUGG_STRIPE_MODE=live` or any `sk_live_`/`pk_live_`/`rk_live_`
key) pending merchant-identity review (issue #159). Backend Stripe env vars:
`HUMBUGG_STRIPE_MODE` (`test`/`disabled`), `HUMBUGG_STRIPE_PUBLISHABLE_KEY`,
`HUMBUGG_STRIPE_SECRET_KEY`, `HUMBUGG_STRIPE_WEBHOOK_SECRET`. Full runbook:
`humbugg/docs/stripe-setup.md`.

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
- `humbugg-audit-events` — standard append-only audit trail for sensitive exchange actions (creation/deletion, participant/exclusion/role/entitlement/reminder changes, draws, resets, reveals, self-service data clears, membership anonymization, and account deletion); see `infra/README.md`. Account deletion never erases audit records — it anonymizes only the `actor_user_id` via the narrow `IAuditActorAnonymizer` seam. Retention/deletion policy is documented in `docs/data-retention-deletion.md`.
- `humbugg-analytics-events` — privacy-safe product-analytics funnel events (plan + aggregate counts only; no wishlist/address/email/token/assignment). Deduped by `idempotency_key`; disable via `HUMBUGG_ANALYTICS_ENABLED=false`; see `docs/analytics.md`
- `humbugg-email-messages` — stable transactional message IDs and delivery state

Profile photos are **not** in DynamoDB: the `humbugg-profiles` row stores only an `avatar_key`
reference, and the image bytes live in the dedicated `humbugg-avatars-production` S3 bucket (Terraform
`avatars` module). Uploads are validated and safely re-encoded to a square, metadata-free JPEG
(`SixLabors.ImageSharp`) before storage; when no photo is set, the frontend renders an initials avatar.

Production tables are accessed through the AWS SDK for .NET directly from the
Lambda (no ORM, no VPC). Local app runs use per-machine AWS DynamoDB tables
and the unsigned shared Mailer API with Mailpit for product email. Mailpit never
relays externally. Unit tests retain the in-memory capture adapter and ledger.
Production signs Mailer API requests with the backend Lambda role, and a
separate status Lambda consumes normalized delivery feedback. Local end-to-end
testing uses the containers. `DynamoDbBootstrap` owns local-only table
bootstrap; repository classes own Humbugg persistence operations.
