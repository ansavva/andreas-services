# Claude Instructions – andreas-services Monorepo

## What this repo is

A monorepo of independently deployed services, all under the `andreas.services` domain.
Each subdirectory is a **fully self-contained deployable unit** — it has its own backend, frontend, infra code, and deployment pipeline. Services do **not** share code or libraries.

## Environment access

**AWS CLI — always use the `personal` profile.** There is no `default` profile, so
a bare `aws ...` command fails with `NoCredentials` (or a misleading "run `aws login`"
hint). Every AWS call must specify the profile:

```bash
export AWS_PROFILE=personal      # once per shell, then use `aws ...` normally
aws --profile personal ...       # or per-command
```

`personal` is AWS account `704202188703` — this is the account that hosts all
`andreas.services` and `humbugg.com` infrastructure. The other configured profile
(`insolvia`, account `521762924626`) is unrelated to this repo; do not use it here.

With the profile set, prefer the CLI for read-only investigation of live
infrastructure (CloudFront, S3, Lambda, DynamoDB, CloudWatch Logs, SSM, etc.) when
diagnosing issues. Note: outbound HTTP to
`*.andreas.services` is blocked by the sandbox network policy (responses look
like `403 host_not_allowed` / "Host not in allowlist"), so use AWS APIs rather
than `curl` against the live sites; final browser verification is on the user.
Prefer fixing infrastructure through Terraform + the deploy pipeline over manual
CLI mutations, to avoid IaC drift.

## Services

| Directory | Purpose | Stack |
|-----------|---------|-------|
| `storybook/` | AI portrait studio | Flask + React/Vite/HeroUI + Lambda (Docker) + DynamoDB |
| `humbugg/` | Gift-exchange platform | ASP.NET Core 10 (C# 14) + React/Vite + Lambda (Docker) + DynamoDB |
| `scout/` | Events from Gmail | Python Lambdas + React/Vite/TS + DynamoDB |
| `infra/` | Shared infrastructure | Terraform |

## Shared Infrastructure (`infra/`)

The root `infra/` directory owns **cross-cutting AWS resources** shared by all services. Never create these inside an individual service's infra:

- **Route53** hosted zone for `andreas.services`
- **ACM wildcard certificate** for `*.andreas.services` (us-east-1, required for CloudFront)

> **Note:** The VPC, NAT Gateway, and DocumentDB cluster have been removed. All services use DynamoDB (IAM-controlled, no VPC required), which eliminates the ~$230/month NAT Gateway cost.

State is in S3: `s3://andreas-services-terraform-state/`
- Shared: `root/terraform.tfstate`
- Per-service: `<service>/<env>/terraform.tfstate` (e.g. `humbugg/prod/`, `scout/prod/`, `scout/pr-preview/`)
- Per-PR ephemeral: `scout/pr/<N>/terraform.tfstate` (key injected at `terraform init` via `-backend-config`)

Services reference shared resources via Terraform data sources — never duplicate them:
```hcl
data "aws_acm_certificate" "wildcard" {
  provider = aws.us_east_1
  domain   = "*.andreas.services"
  statuses = ["ISSUED"]
}

data "aws_route53_zone" "main" {
  name = "andreas.services"
}
```

## Patterns Every Service Follows

### Frontend
- **Build tool**: Vite (not Create React App)
- **Framework**: React 18
- **Styling**: Tailwind CSS (v3 or v4)
- **Language**: TypeScript preferred (Storybook uses strict mode)
- **Folder structure**:
  ```
  frontend/src/
  ├── apis/          # API call wrappers
  ├── components/    # Feature-grouped components
  ├── pages/         # Page-level components
  ├── hooks/         # Custom React hooks
  ├── context/       # React context providers
  ├── utils/         # Pure utility functions
  └── types/         # TypeScript type definitions
  ```
- **Environment variables**: `VITE_` prefix, set as GitHub Actions vars

### Backend (Flask services — e.g. storybook)
- **Framework**: Flask with Blueprint-based routing
- **Pattern**: routes → controllers → services → repositories
- **Logging**: structured JSON (structlog or watchtower → CloudWatch)
- **Auth**: AWS Cognito JWT validation
- **DB access**: DynamoDB via boto3 (no ORM, no VPC needed)

### Backend (ASP.NET Core services — humbugg)
- **Framework**: ASP.NET Core 10 (C# 14), packaged as a Docker container Lambda behind API Gateway HTTP API
- **Pattern**: controllers → services → DynamoDB repositories
- **Auth**: AWS Cognito access-token validation (SRP via Amplify Auth on the SPA)
- **DB access**: DynamoDB via the AWS SDK for .NET (no ORM, no VPC needed)
- **Note**: Humbugg was migrated from Python/Flask to ASP.NET Core — it is no longer a Python service. See `humbugg/CLAUDE.md` for details.

### Backend (Lambda-only services like scout-events)
- **Language**: Python 3.11
- **Logging**: Standard `logging` module; output goes to CloudWatch automatically
- **AWS SDK**: boto3 — never hardcode credentials; rely on IAM role

### Infrastructure
- All services use **Terraform** (`<service>/infra/`). CloudFormation is not used.
- All CloudFront distributions use the shared ACM certificate and Route53 zone from `infra/`
- S3 + CloudFront for all static frontends
- Lambda for all backends (containerised Docker images in ECR — Flask, ASP.NET Core, and pure Lambda functions alike)

### Infrastructure directory naming

All per-service and shared infrastructure directories must be named `infra/` — never `terraform/` or any other name.

### Terraform directory structure

Every service's `infra/` directory must follow this layout:

```
infra/
├── modules/          # One subdirectory per logical concern (auth, storage, compute, hosting, …)
│   └── <module>/
│       ├── main.tf
│       ├── variables.tf
│       └── outputs.tf
└── envs/             # One subdirectory per deployed environment
    └── <env>/        # e.g. prod, pr-preview, pr
        ├── main.tf
        ├── variables.tf
        ├── providers.tf
        ├── backend.tf
        ├── outputs.tf
        └── terraform.tfvars.example
```

- Modules contain reusable resource definitions; environments wire them together with environment-specific values.
- Sensitive variables are declared with `sensitive = true` and passed via `TF_VAR_*` in CI — never committed to the repo.
- `lifecycle { ignore_changes = [image_uri, environment] }` on Lambda resources — the deploy workflow owns both: `update-function-code` for the image and `update-function-configuration` for env vars. Terraform sets initial values on first creation only.

### Deployment (CI/CD)
- **Standard**: GitHub Actions. Filenames follow `<service>-<env>.yaml` (combined deploy) and `<service>-pr.yml` (combined PR workflow) — e.g. `humbugg-prod.yaml`, `scout-pr.yml` — so the service and the trigger environment (PR vs Prod) are visible at a glance. Auxiliary workflows append a scope suffix after the env segment (e.g. `scout-pr-teardown.yaml`, `shared-prod-infra-plan.yaml`).
- **One combined PR workflow per service**: each service has a single `<service>-pr.yml` that runs on every PR. It validates first (lint + unit tests + build); when the service has an ephemeral preview deploy (scout), preview-infra and preview-deploy are separate jobs chained via `needs:` so a failing validate blocks any AWS writes. Scout's PR workflow also reapplies the shared PR-preview infra on every PR so fresh AWS accounts don't need a manual bootstrap.
- **One combined prod deploy per service**: each service has a single `<service>-prod.yaml` with four jobs chained via `needs:`: `detect-changes → build-and-push → deploy-infra → update-lambda + deploy-frontend`. Image build runs **before** Terraform applies because Lambda resources reference `${ecr_repo}:latest` with `lifecycle { ignore_changes = [image_uri, environment] }`, so the image must already exist before Terraform creates the Lambda. Putting build-and-push first eliminates the chicken-and-egg trap on fresh AWS accounts. `update-lambda` then sets env vars and pins the function code to `:${{ github.sha }}` for traceability. This eliminates races between separate infra and app workflows that shared SSM params.
- **Path filtering**: `dorny/paths-filter@v3` — only deploy when the service's files change
- **Separate jobs**: `update-lambda` and `deploy-frontend` run independently after `deploy-infra`
- **AWS auth**: OIDC role assumption (`aws-actions/configure-aws-credentials@v4`) — never long-lived keys
- **Secrets/vars**: GitHub environment secrets and vars; never in code or `.env` files committed to repo
- **Frontend cache-control**:
  - Hashed assets → `public, max-age=31536000, immutable`
  - HTML files → `no-cache, no-store, must-revalidate`
- **CloudFront**: always invalidate `/*` after S3 sync
- **Concurrency groups** (prevent racing deploys to the same environment):
  - `<service>-prod` (`cancel-in-progress: false`) on every prod deploy workflow
  - `scout-preview-pr-<N>` (`cancel-in-progress: true`) on the per-PR preview workflow (covers both the shared preview infra ensure-step and the per-PR deploy) and on the teardown
  - `shared-infra` (`cancel-in-progress: false`) on the shared Terraform apply
- **Chaining on shared infra**: each service's combined prod deploy workflow declares a `workflow_run` trigger on `Shared infra · Terraform apply · Prod` with a job-level guard (`if: github.event_name != 'workflow_run' || github.event.workflow_run.conclusion == 'success'`) so a cert or zone change reapplies every downstream service's infra only when the shared apply succeeds. `workflow_run` doesn't inherit path filters; this is intentional — a shared cert/zone change should reapply everything downstream.
- **Manual triggers**: every combined workflow accepts `workflow_dispatch` inputs `run_infra` (default `true`) and `run_app` (default `true`) for targeted reruns.

## AWS Credentials — Critical Rule

**Never hardcode AWS credentials in any file.**

```python
# CORRECT — boto3 uses Lambda IAM role automatically in AWS, AWS CLI profile locally
boto3.client('s3', region_name='us-east-1')

# WRONG — never do this
boto3.client('s3', aws_access_key_id='AKIA...', aws_secret_access_key='...')
```

## Adding a New Service

1. Create `<service>/` directory — self-contained with own backend, frontend, infra
2. Reference shared Terraform outputs (Route53 zone, ACM cert, VPC) — do not recreate them
3. Add GitHub Actions workflows at `.github/workflows/<service>-<env>.yaml` following the storybook pattern:
   - `<service>-pr.yml` — PR checks (lint, test, Docker build verification); if the service has ephemeral preview deploys, chain them as a job with `needs: <validate-job>` so validation must pass first
   - `<service>-prod.yaml` — single combined deploy (detect-changes → deploy-infra → deploy-backend + deploy-frontend), with `concurrency: { group: <service>-prod, cancel-in-progress: false }`, `workflow_dispatch` inputs `run_infra` and `run_app`, and a `workflow_run` trigger on `Shared infra · Terraform apply · Prod`.
   Use path filtering, OIDC auth, and SSM params for cross-job values.
4. Use Vite for the frontend (not CRA)
5. Add TypeScript
6. Add a `CLAUDE.md` inside the service directory with service-specific context
7. Document subdomain in the service README (e.g., `events.andreas.services`)

## Branch Conventions

Development branches follow the pattern `claude/<feature-name>-<id>`.
Production deployments trigger from `main`.
