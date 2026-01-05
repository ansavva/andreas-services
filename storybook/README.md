# Storybook

Storybook is an AI portrait studio that lets authenticated users upload training photos, organize them into projects, fine-tune a private Replicate model, and generate new images. The system ships two independently deployed components that talk to each other via HTTPS.

## Architecture

- **`backend/`** – Python/Flask API running on AWS Lambda (containerized), secured with AWS Cognito, persists project metadata in MongoDB/DocumentDB, stores images in S3, and orchestrates Replicate trainings/inference. It exposes Blueprints for images, model management, and project CRUD plus health endpoints for monitoring.
- **`frontend/`** – `frontend/storybook-ui` is a Vite + React + NextUI experience (Tailwind-enabled) served via S3 + CloudFront. Handles AWS Cognito authentication and provides project/image management tooling.
- **`terraform/`** – Modular Terraform configuration for provisioning all AWS resources (Lambda, VPC, DocumentDB, S3, CloudFront, Cognito, Route53, etc.)
- **`dev-docs/`** – Development documentation and guides

## Prerequisites

Install the required tooling (Homebrew commands shown for macOS):

- **Python 3.11** – `brew install python@3.11`
- **Node.js 18+** – `brew install node`
- **MongoDB 7.0** (local dev) – `brew tap mongodb/brew && brew install mongodb-community@7.0`

## Run Backend Locally

To run locally:

```bash
# Start MongoDB
brew services start mongodb-community@7.0

# Run backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m src.handlers.local.api.api_dev_server
```

For local development, copy `.env.example` to `.env` and fill in the values from Terraform outputs.

## Run Image Worker Locally

The image processor runs as a local SQS poller. You must set the queue URL.

```bash
cd backend
source venv/bin/activate
python -m src.handlers.local.jobs.poll_image_normalization_handler
```

## Run Frontend Locally

```bash
cd frontend/storybook-ui
npm install
npm run dev
```

For local development, copy `.env.local.example` to `.env.local` and fill in the values from Terraform outputs.

## Deployment

### Automatic Deployment (Recommended)

Push changes to the `main` branch. GitHub Actions will automatically:
- Build and deploy backend to Lambda when `storybook/backend/**` changes
- Build and deploy frontend to S3/CloudFront when `storybook/frontend/**` changes

See [.github/workflows/deploy-storybook.yml](../.github/workflows/deploy-storybook.yml) for details.
