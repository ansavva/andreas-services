# Claude Instructions – andreas-services Monorepo

## What this repo is

A monorepo of independently deployed services, all under the `andreas.services` domain.
Each subdirectory is a **fully self-contained deployable unit** — it has its own backend, frontend, infra code, and deployment pipeline. Services do **not** share code or libraries.

## Services

| Directory | Purpose | Stack |
|-----------|---------|-------|
| `storybook/` | AI portrait studio | Flask + React/Vite/HeroUI + Lambda (Docker) + MongoDB |
| `humbugg/` | Gift-exchange platform | Flask + React/Vite + Lambda + MongoDB |
| `scout/` | Events from Gmail | Python Lambdas + React/Vite/TS + DynamoDB |
| `my-tools/` | Utility scripts | Python |
| `terraform/` | Shared infrastructure | Terraform |

## Shared Infrastructure (`terraform/`)

The root `terraform/` directory owns **cross-cutting AWS resources** shared by all services. Never create these inside an individual service's infra:

- **Route53** hosted zone for `andreas.services`
- **ACM wildcard certificate** for `*.andreas.services` (us-east-1, required for CloudFront)

> **Note:** The VPC, NAT Gateway, and DocumentDB cluster have been removed. All services use DynamoDB (IAM-controlled, no VPC required), which eliminates the ~$230/month NAT Gateway cost.

State is in S3: `s3://andreas-services-terraform-state/`
- Shared: `root/terraform.tfstate`
- Per-service: `<service>/<env>/terraform.tfstate`

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

### Backend (Flask services)
- **Framework**: Flask with Blueprint-based routing
- **Pattern**: routes → controllers → services → repositories
- **Logging**: structured JSON (structlog or watchtower → CloudWatch)
- **Auth**: AWS Cognito JWT validation
- **DB access**: DynamoDB via boto3 (no ORM, no VPC needed)

### Backend (Lambda-only services like scout-events)
- **Language**: Python 3.11
- **Logging**: Standard `logging` module; output goes to CloudWatch automatically
- **AWS SDK**: boto3 — never hardcode credentials; rely on IAM role

### Infrastructure
- Storybook and Humbugg use **Terraform** (`<service>/terraform/`)
- scout-events uses **CloudFormation** — either approach is acceptable for new services
- All CloudFront distributions use the shared ACM certificate and Route53 zone from `terraform/`
- S3 + CloudFront for all static frontends
- Lambda for all backends (containerised Docker for Flask services, zip for pure Lambda)

### Deployment (CI/CD)
- **Standard**: GitHub Actions. Filenames follow `<service>-<env>.yaml` (combined deploy) and `<service>-pr.yml` (combined PR workflow) — e.g. `humbugg-prod.yaml`, `scout-pr.yml` — so the service and the trigger environment (PR vs Prod) are visible at a glance. Auxiliary workflows append a scope suffix after the env segment (e.g. `scout-pr-teardown.yaml`, `shared-prod-infra-plan.yaml`).
- **One combined PR workflow per service**: each service has a single `<service>-pr.yml` that runs on every PR. It validates first (lint + unit tests + build); when the service has an ephemeral preview deploy (scout), preview-infra and preview-deploy are separate jobs chained via `needs:` so a failing validate blocks any AWS writes. Scout's PR workflow also reapplies the shared PR-preview infra on every PR so fresh AWS accounts don't need a manual bootstrap.
- **One combined prod deploy per service**: each service has a single `<service>-prod.yaml` that runs infra then apps in one workflow with `needs:` chaining (detect-changes → deploy-infra → deploy-backend + deploy-frontend). This eliminates races between separate infra and app workflows that shared SSM params.
- **Path filtering**: `dorny/paths-filter@v3` — only deploy when the service's files change
- **Separate jobs**: `deploy-backend` and `deploy-frontend` run independently
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
