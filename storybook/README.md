# Storybook

Storybook is an AI portrait studio that lets authenticated users upload training photos, organize them into projects, fine-tune a private Replicate model, and generate new images. The system ships two independently deployed components that talk to each other via HTTPS.

## Architecture

- **`backend/`** – Python/Flask API running on AWS Lambda (containerized), secured with AWS Cognito, persists project metadata in DynamoDB, stores images in S3, and orchestrates Replicate trainings/inference. It exposes Blueprints for images, model management, and project CRUD plus health endpoints for monitoring.
- **`frontend/`** – `frontend/storybook-ui` is a Vite + React + NextUI experience (Tailwind-enabled) served via S3 + CloudFront. Handles AWS Cognito authentication and provides project/image management tooling.
- **`infra/`** – Modular Terraform configuration for provisioning all AWS resources (Lambda, DynamoDB, S3, CloudFront, Cognito, Route53, etc.)
- **`dev-docs/`** – Development documentation and guides

## Prerequisites

Install the required tooling (Homebrew commands shown for macOS):

- **Python 3.11** – `brew install python@3.11`
- **Node.js 18+** – `brew install node`

## Run Backend Locally

To run locally:

```bash
(cd backend && poetry install)
./scripts/dev-up.sh --backend       # DynamoDB Local :8004 + API :8003
```

The local backend writes to DynamoDB Local on `localhost:8004` and creates the
`storybook-*` tables on startup.

**Every local value lives in one file, `~/.config/andreas-services/storybook/dev.env`**,
documented key by key in [`dev.env.sample`](dev.env.sample). `dev-up.sh` lays it
out from the sample on every run — your values kept, new keys slotted in — and
exports every key into each process (Vite inlines only `VITE_*`). There is no
`backend/.env` or `frontend/storybook-ui/.env.local`. `STORYBOOK_DEV_ENV_FILE`
overrides the location.

## Run Image Worker Locally

The image processor runs as a local SQS poller. Set `IMAGE_UPLOAD_QUEUE_URL` in
`dev.env`, then:

```bash
./scripts/dev-up.sh --worker
```

## Run Frontend Locally

```bash
npm --prefix frontend/storybook-ui install
./scripts/dev-up.sh --frontend      # Vite on :5177, VITE_* from dev.env
```

Fill the `VITE_AWS_COGNITO_*` keys in `dev.env` from the Terraform outputs of a
dev apply.

## Deployment

### Automatic Deployment (Recommended)

Push changes to the `main` branch. GitHub Actions runs a single combined workflow that:
- Applies Terraform when `storybook/infra/**` changes
- Builds and deploys the backend (api + image-worker Lambdas) when `storybook/backend/**` changes or infra ran
- Builds and deploys the frontend to S3/CloudFront when `storybook/frontend/**` changes or infra ran

See [.github/workflows/storybook-prod.yaml](../.github/workflows/storybook-prod.yaml) for details.
