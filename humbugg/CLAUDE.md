# Claude Instructions – humbugg

## What this service does

Humbugg is a gift-exchange platform, served from three hostnames:

| Surface | URL | What it is |
|---|---|---|
| Marketing | `www.humbugg.com` | React Router v7 SSR. The apex 308s to it. |
| Product app | `app.humbugg.com` | Expo + Expo Router, deployed as a static web export. The same codebase builds iOS/Android later. |
| API | `api.humbugg.com` | ASP.NET Core Lambda behind an API Gateway custom domain. |

What it does:

1. Organizers create a group, invite members, and each member fills in a wish list / "do-not-give" list.
2. A matching engine assigns each member a recipient (Secret Santa-style) while respecting exclusions.
3. Members sign in via AWS Cognito and see their assignment in the React SPA.

## Stack

| Layer | Choice |
|---|---|
| Backend | ASP.NET Core 10 (C# 14) packaged as a Docker container Lambda behind API Gateway HTTP API, on its own domain |
| Marketing (`web/`) | React Router v7 SSR on a Docker Lambda + CloudFront; hashed assets on S3. Vite, Tailwind v4, the design system's **web** leaves |
| Product app (`app/`) | Expo + Expo Router; `expo export -p web` → S3 + CloudFront. Metro, **no Tailwind**, the design system's **native** leaves rendered through react-native-web |
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
├── web/                        # Marketing site — React Router v7 SSR (www.humbugg.com)
│   ├── app/                     # routes, including the legacy → app redirects
│   ├── src/                     # pages, Layout, config
│   └── vite.config.ts
├── app/                        # Product app — Expo + Expo Router (app.humbugg.com)
│   ├── app/                     # file-based routes
│   ├── src/                     # api client, contexts, theme
│   └── app.json
├── infra/                      # Terraform
│   ├── modules/                # auth, compute, hosting, storage
│   └── envs/prod/              # Lambda + API Gateway + Cognito, S3 + CloudFront + Route53 alias
└── CLAUDE.md                   # ← this file
```

## Shared Infrastructure

Terraform references (but doesn't own) two shared resources via `data` sources:

- **Route53 hosted zone** (`humbugg.com`) — a Terraform data source

`modules/certificates` provisions one us-east-1 ACM certificate covering the
apex, `www`, `app` and `api`. It is shared by both CloudFront distributions and
the API Gateway custom domain — us-east-1 does double duty here, being both
CloudFront's required region and this deployment's own region.

Two distributions: `modules/hosting_marketing` serves marketing (aliases apex and
`www`; a CloudFront function 308s everything that is not `www` to it) and
`modules/hosting_app` serves the product app plus `/avatars/*`.

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

# Authenticate npm for the private design system package. This reads your
# existing gh login when it carries read:packages; export
# GITHUB_PACKAGES_TOKEN=<pat> first only where gh is not signed in (CI, sandbox).
eval "$(./scripts/github-packages-auth.sh --export)"
npm --prefix humbugg/marketing install
npm --prefix humbugg/app install

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
| `humbugg/scripts/dev-up-marketing.sh` | Marketing-site-only startup; validates `web/.env.local` and installed dependencies first |
| `humbugg/scripts/dev-up-app.sh` | Product-app-only startup; defaults to `--web`, pass `--ios`/`--android` for a simulator |
| `humbugg/scripts/dev-up-stripe.sh` | Stripe-only listener for the billing webhook's exact event allowlist; copy its `whsec_...` value into `backend/.env` and restart the backend when running components separately |
| `humbugg/scripts/dev-logs-backend.sh` | Follow the backend container logs; accepts Docker Compose log options such as `--tail 200` |
| `humbugg/scripts/dev-user.sh` | Create or converge the dev-stack test account; `--generate-password` for a non-interactive run, `--check` to report without changing. **Both halves live in `~/.config/andreas-services/humbugg/dev.env`** — `HUMBUGG_DEV_USER_EMAIL` and `HUMBUGG_DEV_USER_PASSWORD`. No address is committed; a reserved `.test` one is what belongs there |
| `humbugg/scripts/dev-aws-reset.sh` | Destructive data reset scoped to this machine; run with `--dry-run` first; `--skip-cognito` preserves users |
| `humbugg/scripts/dev-aws-destroy.sh` | Destroy this machine's AWS resources; the persistent UUID is deliberately retained |

`humbugg/scripts/dev-aws-common.sh` is a sourced implementation helper, not a
user command. AWS commands default to `$AWS_PROFILE`/`default` and
`$AWS_REGION`/`$AWS_DEFAULT_REGION`/`us-east-1`; the `default` profile is the
right one for this repo, so `--profile` is only needed to override it.

To start components separately:

```bash
./humbugg/scripts/dev-up-backend.sh                     # http://localhost:5001
./humbugg/scripts/dev-up-marketing.sh                         # http://localhost:5173
./humbugg/scripts/dev-up-app.sh                         # http://localhost:8081
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

`dev-aws-setup.sh` generates two ignored env files — the prefixes differ because
the bundlers do (Vite exposes `VITE_*`, Metro inlines `EXPO_PUBLIC_*`). Do not
create shared or committed values manually.

`web/.env.local` — no Cognito values, because the marketing site no longer
authenticates anyone:

```
VITE_APP_BASE_URL=http://localhost:5173
VITE_APP_ORIGIN=http://localhost:8081
```

`app/.env.local`:

```
EXPO_PUBLIC_COGNITO_USER_POOL_ID=<generated by scripts/dev-aws-setup.sh>
EXPO_PUBLIC_COGNITO_CLIENT_ID=<generated by scripts/dev-aws-setup.sh>
EXPO_PUBLIC_AWS_REGION=us-east-1
EXPO_PUBLIC_API_BASE_URL=http://127.0.0.1:5001/api
```

The app calls the backend **cross-origin** in development as well as production,
so the backend's `CORS_ORIGINS` must list `http://localhost:8081` alongside
`http://localhost:5173`.

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
| _(env var, not SSM)_ `HUMBUGG_APP_BUCKET` | Shared application object bucket (`humbugg-prod-app-files-us-east-1`, the `app_files` bucket in the `storage` module); set literally in `update-lambda`. Profile photos live under the `avatars/` prefix — private, written by the Lambda under `avatars/*` (least-privilege IAM) and served read-only at `/avatars/*` through the app CloudFront distribution via OAC. Local development uses the per-machine AWS bucket created by `scripts/dev-aws-setup.sh`. Avatar URLs derive from `APP_BASE_URL` unless `HUMBUGG_AVATAR_BASE_URL` overrides it. |
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
                       ├─► update-lambda           (backend + marketing SSR env vars, pin to :sha)
                       ├─► deploy-frontend-assets  (if humbugg/marketing/** changed OR infra ran)
                       └─► deploy-app              (if humbugg/app/** changed OR infra ran)
```

App jobs use `needs: [detect-changes, deploy-infra]` and an `if:` that runs when the app changed OR when `deploy-infra` produced new SSM values. If `deploy-infra` is skipped (app-only change) the app jobs still run because `!cancelled() && needs.deploy-infra.result != 'failure'` is true for skipped upstream jobs.

**`workflow_dispatch` inputs**

- `run_infra` (default `true`) — run the `deploy-infra` job.
- `run_app` (default `true`) — run `deploy-backend` and `deploy-frontend`.

Use `run_infra=true, run_app=false` for infra-only reruns, and `run_infra=false, run_app=true` to redeploy just the app using whatever is already in SSM.

**Concurrency**

Group `humbugg-prod` with `cancel-in-progress: false` — queued pushes wait for the previous run instead of racing on `update-function-code` or SSM writes.

## DynamoDB Tables

- `humbugg-prod-profiles` — per-user profile and wish-list data
- `humbugg-prod-groups` — group metadata (owner, name, member list)
- `humbugg-prod-groupmembers` — group ↔ member relationship + assignment results
- `humbugg-prod-draws` — private giver → recipient maps, separate from ordinary group responses
- `humbugg-prod-audit-events` — standard append-only audit trail for sensitive exchange actions (creation/deletion, participant/exclusion/role/entitlement/reminder changes, draws, resets, reveals, self-service data clears, membership anonymization, and account deletion); see `infra/README.md`. Account deletion never erases audit records — it anonymizes only the `actor_user_id` via the narrow `IAuditActorAnonymizer` seam. Retention/deletion policy is documented in `docs/data-retention-deletion.md`.
- `humbugg-prod-analytics-events` — privacy-safe product-analytics funnel events (plan + aggregate counts only; no wishlist/address/email/token/assignment). Deduped by `idempotency_key`; disable via `HUMBUGG_ANALYTICS_ENABLED=false`; see `docs/analytics.md`
- `humbugg-prod-email-messages` — stable transactional message IDs and delivery state

Profile photos are **not** in DynamoDB: the `humbugg-prod-profiles` row stores only an `avatar_key`
reference, and the image bytes live under the `avatars/` prefix of the shared application object
bucket `humbugg-prod-app-files-us-east-1` (Terraform `storage` module, `app_files` bucket — there is
no separate avatars bucket or module). Uploads are validated and safely re-encoded to a square, metadata-free JPEG
(`SixLabors.ImageSharp`) before storage; when no photo is set, the frontend renders an initials avatar.

Production tables are accessed through the AWS SDK for .NET directly from the
Lambda (no ORM, no VPC). Local app runs use per-machine AWS DynamoDB tables
and the unsigned shared Mailer API with Mailpit for product email. Mailpit never
relays externally. Unit tests retain the in-memory capture adapter and ledger.
Production signs Mailer API requests with the backend Lambda role, and a
separate status Lambda consumes normalized delivery feedback. Local end-to-end
testing uses the containers. `DynamoDbBootstrap` owns local-only table
bootstrap; repository classes own Humbugg persistence operations.
