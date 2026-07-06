# Setup & deployment

## Prerequisites

- Node 20, npm 10 (the frontend targets the Node 20 Lambda runtime; do **not**
  upgrade to React Router v8, which requires Node 22).
- Python 3.11 + Poetry (backend).
- Docker (to validate both Lambda images locally).
- Terraform ≥ 1.5, AWS CLI authenticated.
- A GitHub token with **`read:packages`** to install `@ansavva/design-system`
  from GitHub Packages: `gh auth refresh -h github.com -s read:packages`.

## Local development

### Frontend (SSR)

```bash
cd frontend
export NODE_AUTH_TOKEN=$(gh auth token)   # read:packages scope
npm ci
npm run dev        # http://localhost:5173
```

Marketing + blog pages render without a backend. The intake/newsletter forms and
`/admin` need `WEBSITE_API_URL` (+ `COGNITO_*`, `SESSION_SECRET`) pointing at a
running backend — set them in `.env` (see `../.env.example`).

Type-check / lint / build:

```bash
npm run typecheck && npm run lint && npm run build
```

### Backend (Python API)

```bash
cd backend/api
poetry install
poetry run pytest        # moto-backed unit tests
```

### Validate the Lambda images (Docker)

```bash
# Backend
cd backend/api && docker build -t website-api:local .
# Frontend (build first so build/ exists)
cd ../../frontend && npm run build && docker build -t website-ssr:local .
```

Each base image ships the Lambda Runtime Interface Emulator; invoke locally with
`curl -XPOST localhost:9000/2015-03-31/functions/function/invocations -d @event.json`.

## Deployment (GitHub Actions)

`.github/workflows/website-prod.yaml` runs on push to `main` (paths `website/**`):
`detect-changes → build-and-push (both images) → deploy-infra (Terraform) →
update-lambda + deploy-frontend-assets + bootstrap-admin`.

Images are built **before** Terraform (Lambdas reference `:latest` with
`ignore_changes=[image_uri,environment]`), then pinned to the commit SHA.

### GitHub `website-production` environment

`AWS_ROLE_ARN` is a **repository-level** secret (shared by every service) and is
inherited by this environment — do **not** re-add it. The shared `github_actions`
IAM role already covers the website's resources. Only the website-specific
secrets/vars below need to be added to the environment.

**Secrets**

| Secret | Purpose |
|--------|---------|
| `KIT_API_KEY`, `KIT_FORM_ID` | Newsletter (Kit/ConvertKit) — backend env |
| `SESSION_SECRET` | A random string **you generate** (`openssl rand -base64 32`) that signs the admin login cookie so it can't be forged — frontend env |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Bootstraps the single Cognito admin user |

**Variables**

| Variable | Purpose |
|----------|---------|
| `VITE_GA_MEASUREMENT_ID` | GA4 (baked into the client bundle at build) |
| `VITE_CAL_LINK` | Cal.com handle for the booking embed |

`NODE_AUTH_TOKEN` for the frontend build uses the workflow's `secrets.GITHUB_TOKEN`
with `permissions: packages: read` (no PAT needed in CI).

The deploy workflow sets each Lambda's runtime env via
`update-function-configuration` (Terraform only sets minimal values on first
create). Frontend env: `WEBSITE_API_URL`, `COGNITO_USER_POOL_ID`,
`COGNITO_CLIENT_ID`, `SESSION_SECRET`. Backend env: `WEBSITE_TABLE_SUFFIX`,
`WEBSITE_ALLOWED_ORIGIN`, `KIT_API_KEY`, `KIT_FORM_ID`.

## Admin user

The dashboard at `/admin` is a single Cognito user (no self-signup). CI runs
`scripts/create-admin-user.sh` after infra applies; to do it manually:

```bash
USER_POOL_ID=<pool-id> ADMIN_EMAIL=you@example.com ADMIN_PASSWORD='...' \
  ./scripts/create-admin-user.sh
```

## Notes

- No SES: intake submissions are stored in DynamoDB and read via `/admin`.
- The shared `*.andreas.services` wildcard cert (SAN includes the apex) covers
  both `www` and the apex alias — nothing extra to provision.
- First apply: because Lambdas reference `:latest`, the images must exist in ECR
  before Terraform creates the functions. The workflow's `build-and-push` job
  guarantees this.
