# Storybook

Storybook is an AI portrait studio that lets authenticated users upload training photos, organize them into projects, fine-tune a private Replicate model, and generate new images. The system ships two independently deployed components that talk to each other via HTTPS.

## Live URLs

- **Frontend**: [https://storybook.andreas.services/app](https://storybook.andreas.services/app)
- **Backend API**: [https://api.storybook.andreas.services](https://api.storybook.andreas.services)

## Architecture

- **`backend/`** – Python/Flask API running on AWS Lambda (containerized), secured with AWS Cognito, persists project metadata in AWS S3, and orchestrates Replicate trainings/inference. It exposes Blueprints for images, model management, and project CRUD plus health endpoints for monitoring.
- **`frontend/`** – `frontend/storybook-ui` is a Vite + React + NextUI experience (Tailwind-enabled) served via S3 + CloudFront. Handles AWS Cognito authentication and provides project/image management tooling.
- **`infra/`** – Terraform configuration for provisioning all AWS resources (Lambda, S3, CloudFront, Cognito, Route53, etc.)
- **`scripts/`** – Helper scripts for deployment and Cognito setup

### AWS Infrastructure

- **Frontend Hosting**: S3 bucket + CloudFront distribution
- **Backend Runtime**: Lambda function with container image from ECR
- **Authentication**: Cognito User Pool with OAuth 2.0
- **Storage**: Dedicated S3 bucket for user uploads and project data
- **DNS**: Route53 records in the `andreas.services` hosted zone
- **API Gateway**: HTTP API (v2) for custom domain and routing

## Prerequisites

Install the required tooling (Homebrew commands shown for macOS):

- **Python 3.11** – `brew install python@3.11`
- **Node.js 18+** – `brew install node`

## Backend notes

- Requires Python 3.11+, `pip install -r backend/requirements.txt`.
- Environment variables drive secrets (see `backend/src/config.py` and `.env`): `S3_BUCKET_NAME`, AWS credentials, `AWS_COGNITO_REGION`, `AWS_COGNITO_USER_POOL_ID`, `AWS_COGNITO_APP_CLIENT_ID`, Replicate tokens, etc.
- `src/app.py` bootstraps the Flask app with per-request Cognito authentication, registers controllers, and binds to port 8080 by default.
- Services coordinate AWS S3 file storage (`ImageService`/`S3Repo`) and Replicate training/generation (`ModelService`).

To run locally:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
FLASK_ENV=development python src/app.py
```

## Frontend notes

- Located at `frontend/storybook-ui`, scaffolded with Vite/React/TypeScript and NextUI components.
- Uses Tailwind CSS + Tailwind Variants and Framer Motion for interactions.
- Standard Vite commands apply:

```bash
cd frontend/storybook-ui
npm install
npm run dev
```

For local development, copy `.env.local.example` to `.env.local` and fill in the Cognito values from Terraform outputs.

## Deployment

### Automatic Deployment (Recommended)

Push changes to the `main` branch. GitHub Actions will automatically:
- Build and deploy backend to Lambda when `storybook/backend/**` changes
- Build and deploy frontend to S3/CloudFront when `storybook/frontend/**` changes

See [.github/workflows/deploy-storybook.yml](../.github/workflows/deploy-storybook.yml) for details.

### Manual Deployment

**Initial Infrastructure Setup:**
```bash
cd infra
terraform init
terraform plan
terraform apply
```

See [infra/README.md](infra/README.md) for detailed infrastructure setup instructions.

**Backend Deployment:**
```bash
./scripts/deploy-backend.sh
```

**Frontend Deployment:**
```bash
./scripts/deploy-frontend.sh
```

**Cognito Setup (create admin user):**
```bash
./scripts/setup-cognito.sh
```

## Environment Variables

### Backend (Lambda Environment Variables - set via Terraform)
- `FLASK_ENV` - Environment (production/development)
- `AWS_COGNITO_REGION` - AWS region for Cognito
- `AWS_COGNITO_USER_POOL_ID` - Cognito User Pool ID
- `AWS_COGNITO_APP_CLIENT_ID` - Cognito App Client ID
- `S3_BUCKET_NAME` - S3 bucket for user files
- `AWS_REGION` - AWS region
- `REPLICATE_API_TOKEN` - Replicate API token
- `APP_URL` - Frontend URL

### Frontend (Build-time Environment Variables)
- `VITE_API_URL` - Backend API URL
- `VITE_AWS_COGNITO_REGION` - AWS region
- `VITE_AWS_COGNITO_USER_POOL_ID` - Cognito User Pool ID
- `VITE_AWS_COGNITO_APP_CLIENT_ID` - Cognito App Client ID
- `VITE_AWS_COGNITO_DOMAIN` - Cognito domain

## GitHub Actions Setup

Required repository secrets:
- `AWS_ROLE_ARN` - IAM role for GitHub Actions (OIDC)
- `VITE_API_URL` - Backend API URL
- `VITE_AWS_COGNITO_REGION` - Cognito region
- `VITE_AWS_COGNITO_USER_POOL_ID` - From Terraform output
- `VITE_AWS_COGNITO_APP_CLIENT_ID` - From Terraform output
- `VITE_AWS_COGNITO_DOMAIN` - From Terraform output

## Project Structure

```
storybook/
├── backend/              # Flask API (Lambda)
│   ├── src/             # Application code
│   ├── Dockerfile       # Lambda container image
│   ├── lambda_handler.py # Lambda entry point
│   └── requirements.txt # Python dependencies
├── frontend/            # React frontend
│   └── storybook-ui/   # Vite app
├── infra/              # Terraform configuration
│   ├── main.tf         # Provider configuration
│   ├── cognito.tf      # Cognito resources
│   ├── lambda.tf       # Lambda and API Gateway
│   ├── s3.tf           # S3 buckets
│   ├── cloudfront.tf   # CloudFront distribution
│   ├── route53.tf      # DNS records
│   └── README.md       # Infrastructure docs
└── scripts/            # Deployment helpers
    ├── deploy-backend.sh
    ├── deploy-frontend.sh
    └── setup-cognito.sh
```
