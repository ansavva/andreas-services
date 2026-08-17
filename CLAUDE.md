# Claude Instructions – andreas-services Monorepo

## What this repo is

A monorepo of independently deployed services, all under the `andreas.services` domain.
Each subdirectory is a **fully self-contained deployable unit** — it has its own backend, frontend, infra code, and deployment pipeline. Services do **not** share code or libraries.

## Environment access

**AWS CLI — use the `default` profile.** A bare `aws ...` command is correct; no
`--profile` flag is needed:

```bash
aws sts get-caller-identity
```

`default` is AWS account `704202188703` (`user/ansavva`) — the account that hosts
all `andreas.services` and `humbugg.com` infrastructure. If a command fails with
`NoCredentials` or an expired-session error, re-authenticate with `aws login`.

**Running Terraform locally? Export the credentials first.**

```bash
eval "$(aws configure export-credentials --format env)"
```

`aws login` writes its session to a cache only the AWS CLI reads. Terraform's
S3 **backend** resolves it; the AWS **provider** does not. So Terraform
half-works, and which half you get depends on the subcommand:

| Subcommand | Needs | Without the export |
| --- | --- | --- |
| `init`, `state list`, `state show`, `state rm`, `state mv` | backend | works |
| `import`, `plan`, `apply`, `destroy` | provider | fails |

The failure reads as an environment problem and is not:

```
Error: No valid credential sources found
failed to refresh cached credentials, no EC2 IMDS role found,
operation error ec2imds: GetMetadata, ... dial tcp 169.254.169.254:80: connect: host is down
```

**Do not read that as an expired session and run `aws login` again.** `aws sts
get-caller-identity` succeeding proves nothing about it — the CLI is the half
that works. This cost a half-finished state migration in August 2026: a
`state rm` succeeded, the `terraform import` on the very next line failed, and
the error was misread as session expiry three times before the split was found.

Sessions are also short (under ~15 minutes), so export at the point of use
rather than once at the start of a long session. In CI none of this applies:
`aws-actions/configure-aws-credentials` puts real credentials in the
environment, which is why the pipeline never sees this.

Prefer the CLI for read-only investigation of live
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
| `humbugg/` | Gift-exchange platform | ASP.NET Core 10 (C# 14) + React/Vite (marketing, `www`) + Expo/Expo Router (product app, `app`) + Lambda (Docker) + DynamoDB |
| `scout/` | Events from Gmail | Python Lambdas + React/Vite/TS + DynamoDB |
| `studio/` | AI media generation pipeline **and** a browser over its output | Claude Code skills (local, `uv`) + Flask + React/Vite/TS + Lambda (Docker) + Cognito + S3 (no database) |
| `infra/` | Shared infrastructure | Terraform |

**`studio/` breaks two of this repo's rules, both deliberately.** It runs
**local against prod** — one media bucket, one Cognito pool, no dev
environment — because it is a view onto a single library of generated media
and an empty second copy would exercise none of the behaviour that matters. A
delete run locally is a delete in production; bucket versioning without
`s3:DeleteObjectVersion` is what makes that recoverable. See
`studio/CLAUDE.md`. And:

**`studio/` is the one service that is not purely a deployable unit.** Half of it
— `studio/.claude/skills/`, sixteen skills — runs locally inside Claude on a
developer's machine and never deploys; the CI path filters exclude it from the
prod workflow. The other half is an ordinary Flask + Vite service. Both share the
media S3 bucket, which `studio/infra/modules/media` owns. It is also the one
bucket whose name predates the naming convention below and is deliberately
grandfathered — see `studio/infra/README.md`.

**Those skills come in two families, and picking one is the first step of any
task in `studio/`** — route by what the task changes, not what it mentions:

| Changing… | Load |
|---|---|
| media or an S3 record (an image, a clip, a character, a project, a run) | a **`studio-media-*`** skill |
| studio's own code (`pipeline/`, `backend/`, `frontend/`, `infra/`) | **`studio-code-pipeline`** |

Load it with the Skill tool rather than skimming its `SKILL.md` — these pages
lead with concepts and put the runnable commands lower, so reading the first
screen and starting work tends to end in hand-rolled `aws s3` calls that a
`studio` subcommand already does. Full routing table in
[studio/CLAUDE.md](studio/CLAUDE.md#which-skill).

Those sixteen skills live in `studio/.claude/skills/` and are directory-scoped:
they register only once a file under `studio/` has been read, so a `Skill` call
on the first action of a session returns `Unknown skill`. That is a timing
artifact, not a missing skill. The root **`studio`** skill is the entry point —
it is registered from the start and routes you through
[studio/CLAUDE.md](studio/CLAUDE.md#which-skill), which is also the read that
registers the rest.

## Shared Infrastructure (`infra/`)

The root `infra/` directory owns **cross-cutting AWS resources** shared by all services. Never create these inside an individual service's infra:

- **Route53** hosted zone for `andreas.services`
- **ACM wildcard certificate** for `*.andreas.services` (us-east-1, required for CloudFront)

> **Note:** The VPC, NAT Gateway, and DocumentDB cluster have been removed. All services use DynamoDB (IAM-controlled, no VPC required), which eliminates the ~$230/month NAT Gateway cost.

State is in S3: `s3://andreas-services-terraform-state/`
- Shared: `shared/terraform.tfstate`
- Per-service: `<service>/<env>/terraform.tfstate` (e.g. `humbugg/prod/`, `scout/prod/`)

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
- **Design system**: all UI comes from **`@ansavva/design-system`**, published from the separate
  [ansavva/design-system](https://github.com/ansavva/design-system) repo. There is no local component
  library in this monorepo and there must not become one. **Read the `design-system-ui` skill before
  adding or changing any screen, form, dialog or styled component** — it covers the catalogue, the
  platform-leaf import rule, and the theming seams that carry each service's brand.
- **Build tool**: Vite (not Create React App) for web surfaces. **Expo + Metro** for
  React Native surfaces — `humbugg/app` is the first, built so the same codebase can
  ship to the app stores later. The bundler is what selects the design system's
  platform leaf, so this choice is not cosmetic.
- **Framework**: React 18
- **Styling**: Tailwind CSS (v3 or v4) on Vite surfaces. Expo surfaces have **no
  Tailwind pipeline** — they use React Native `StyleSheet` and the design system's
  `ThemeProvider`.
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

### AWS resource naming

Every AWS resource is named `[project]-[env]-[component]-[identifier]` — lowercase
kebab, environment always **second** (`prod` / `dev`), component
named for what it **serves** rather than which tier it sits in. S3 buckets take a
region suffix because their names are globally unique
(`humbugg-prod-marketing-us-east-1`).

Most resources are just `[project]-[env]-[component]`. These need more:

| Resource | Pattern | Example |
| --- | --- | --- |
| **S3 bucket** | `[project]-[env]-[component]-[region]` | `humbugg-prod-marketing-us-east-1` |
| **IAM role** | `[project]-[env]-[component]-role` | `humbugg-prod-api-role` |
| **IAM policy** | `[project]-[env]-[component]-[grant]` | `humbugg-prod-api-dynamodb` |
| **SQS DLQ** | `[project]-[env]-[component]-dlq` | `mailer-prod-feedback-dlq` |
| **CloudFront OAC** | `[project]-[env]-[component]-oac` | `humbugg-prod-app-files-oac` |
| **Log group** | `/aws/lambda/[function-name]` | derived — never hand-written |
| **SSM parameter** | `/[project]/[env]/[name]` | `/humbugg/prod/api-domain` |

Names describe identity; **tags** carry everything else. Every resource that
supports tagging gets all four of `Project`, `Environment`, `Owner`, `ManagedBy`,
set once in `local.common_tags` and passed into every module. Don't add a fifth
name segment for something a tag should hold.

**Renaming is a destroy-and-recreate for most resources.** Lambda, IAM, API
Gateway, log groups, alarms and SSM parameters lose nothing. A Cognito pool
loses every account and password, a DynamoDB table every row, an S3 bucket
every object, an SQS queue its in-flight messages, and an SES identity its
verification. Renaming a Terraform *address* is free and costs nothing when
done with a `moved` block — only a change to the `name`/`bucket`/`function_name`
argument replaces the AWS resource.

**"Loses nothing" is not the same as "succeeds".** ECR repositories and
CloudFront functions carry no data worth keeping and still fail the destroy:
`DeleteRepository` refuses a repository holding images, and CloudFront refuses
to delete a function, OAC or policy a distribution still references. Both broke
a prod deploy in August 2026 (#226, #227).

The fix depends on which kind of failure it is, and the difference matters:

- **`force_delete` / `force_destroy` do not work on the rename that adds them.**
  Terraform applies the destroy half of a replacement against *prior state*, not
  the new configuration — the destroy node gets the old object with `Config`
  null — so the provider reads the flag recorded in state and never sees the
  `true` you just wrote next to the new name. Set the flag, apply, *then*
  rename. Measured, not assumed: renaming a bucket and setting
  `force_destroy = true` in one apply fails `BucketNotEmpty`; doing it in two
  applies succeeds.
- **`create_before_destroy` does work immediately**, because it changes
  Terraform's ordering rather than an argument read off the old object. It is
  the fix for anything a live resource still references — CloudFront functions,
  OACs and origin request policies attached to a distribution.

So: give every ECR repository `force_delete = true` and every regenerable
bucket `force_destroy = true` *when you create it*, and give CloudFront config
objects `create_before_destroy`. Retrofitting them during a rename is too late,
and the recovery is out-of-band state surgery.

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
    └── <env>/        # e.g. prod, dev
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
- **Standard**: GitHub Actions. Filenames follow `<service>-<env>.yaml` (combined deploy) and `<service>-pr.yml` (combined PR workflow) — e.g. `humbugg-prod.yaml`, `scout-pr.yml` — so the service and the trigger environment (PR vs Prod) are visible at a glance. Auxiliary workflows append a scope suffix after the env segment (e.g. `shared-prod-infra-plan.yaml`).
- **One combined PR workflow per service**: each service has a single `<service>-pr.yml` that runs on every PR. It validates only — lint, unit tests, Terraform validate, and a build to prove the image compiles. **PR workflows never write to AWS.** There are no ephemeral preview environments; they were removed because the maintenance and teardown cost outweighed their value for a solo repo.
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
   - `<service>-pr.yml` — PR checks only (lint, test, Terraform validate, Docker build verification). No AWS writes.
   - `<service>-prod.yaml` — single combined deploy (detect-changes → deploy-infra → deploy-backend + deploy-frontend), with `concurrency: { group: <service>-prod, cancel-in-progress: false }`, `workflow_dispatch` inputs `run_infra` and `run_app`, and a `workflow_run` trigger on `Shared infra · Terraform apply · Prod`.
   Use path filtering, OIDC auth, and SSM params for cross-job values.
4. **Add `arn:aws:ssm:*:*:parameter/<service>/*` to the SSM statement in
   `infra/envs/shared/main.tf`.** It is the only resource-scoped statement in the
   CI role's policy, and it is applied by a *different* workflow, so forgetting it
   is invisible until the end of the new service's first `terraform apply` — which
   by then has already created the CloudFront distribution. Add it in the same PR
   as the service, and expect the shared apply to run before the service deploy
   can succeed.
5. Use Vite for the frontend (not CRA)
6. Add TypeScript
7. Add a `CLAUDE.md` inside the service directory with service-specific context
8. Document subdomain in the service README (e.g., `events.andreas.services`)

## Branch Conventions

Development branches follow the pattern `claude/<feature-name>-<id>`.
Production deployments trigger from `main`.
