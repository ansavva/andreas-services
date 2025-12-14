# Storybook

Storybook is an AI portrait studio that lets authenticated users upload training photos, organize them into projects, fine-tune a private Replicate model, and generate new images. The system ships two independently deployed components that talk to each other via HTTPS.

## Live URLs

- **Frontend**: [https://storybook.andreas.services/app](https://storybook.andreas.services/app)
- **Backend API**: [https://api.storybook.andreas.services](https://api.storybook.andreas.services)

## Architecture

- **`backend/`** – Python/Flask API running on AWS Lambda (containerized), secured with AWS Cognito, persists project metadata in MongoDB/DocumentDB, stores images in S3, and orchestrates Replicate trainings/inference. It exposes Blueprints for images, model management, and project CRUD plus health endpoints for monitoring.
- **`frontend/`** – `frontend/storybook-ui` is a Vite + React + NextUI experience (Tailwind-enabled) served via S3 + CloudFront. Handles AWS Cognito authentication and provides project/image management tooling.
- **`terraform/`** – Modular Terraform configuration for provisioning all AWS resources (Lambda, VPC, DocumentDB, S3, CloudFront, Cognito, Route53, etc.)
- **`dev-docs/`** – Development documentation and guides

### AWS Infrastructure

- **Frontend Hosting**: S3 bucket + CloudFront distribution
- **Backend Runtime**: Lambda function with container image from ECR (in VPC for DocumentDB access)
- **Authentication**: Cognito User Pool with OAuth 2.0
- **Database**: MongoDB (local dev) / AWS DocumentDB (production) for project and image metadata
- **File Storage**: Dedicated S3 bucket for user image uploads
- **Networking**: VPC with private subnets for Lambda and DocumentDB communication
- **DNS**: Route53 records in the `andreas.services` hosted zone
- **API Gateway**: HTTP API (v2) for custom domain and routing

## Prerequisites

Install the required tooling (Homebrew commands shown for macOS):

- **Python 3.11** – `brew install python@3.11`
- **Node.js 18+** – `brew install node`
- **MongoDB 7.0** (local dev) – `brew tap mongodb/brew && brew install mongodb-community@7.0`

## Backend notes

- Requires Python 3.11+, `pip install -r backend/requirements.txt`.
- Environment variables drive secrets (see `backend/src/config.py` and `.env`): `DATABASE_URL`, `DATABASE_NAME`, `S3_BUCKET_NAME`, AWS credentials, `AWS_COGNITO_REGION`, `AWS_COGNITO_USER_POOL_ID`, `AWS_COGNITO_APP_CLIENT_ID`, Replicate tokens, etc.
- `src/app.py` bootstraps the Flask app with per-request Cognito authentication, initializes MongoDB connection, registers controllers, and binds to port 5000 by default.
- Data layer uses MongoDB for project/image metadata (`ProjectRepo`, `ImageRepo`/`database.py`) and S3 for actual image files.
- Services coordinate database operations, S3 file storage, and Replicate training/generation (`ModelService`).

To run locally:

```bash
# Start MongoDB
brew services start mongodb-community@7.0

# Run backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
FLASK_ENV=development python -m src.app
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
# For production environment
cd terraform/envs/prod
terraform init
terraform plan
terraform apply
```

See [terraform/README.md](terraform/README.md) for detailed infrastructure setup instructions.

**Backend & Frontend Deployment:**

See GitHub Actions workflow in `.github/workflows/` for automated deployment, or refer to deployment documentation in `dev-docs/`.

## Environment Variables

### Backend (Lambda Environment Variables - set via Terraform)
- `FLASK_ENV` - Environment (production/development)
- `DATABASE_URL` - MongoDB connection string (local: `mongodb://localhost:27017/storybook_dev`, prod: DocumentDB endpoint)
- `DATABASE_NAME` - Database name (default: `storybook_dev`)
- `AWS_COGNITO_REGION` - AWS region for Cognito
- `AWS_COGNITO_USER_POOL_ID` - Cognito User Pool ID
- `AWS_COGNITO_APP_CLIENT_ID` - Cognito App Client ID
- `S3_BUCKET_NAME` - S3 bucket for user image files
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
├── backend/                    # Flask API (Lambda)
│   ├── src/
│   │   ├── controllers/       # API endpoints (Blueprints)
│   │   ├── data/              # Data access layer (repos, database)
│   │   ├── models/            # Domain models (Project, Image)
│   │   ├── services/          # Business logic
│   │   ├── storage/           # File storage abstraction (S3, filesystem)
│   │   ├── app.py             # Flask application
│   │   └── config.py          # Configuration
│   ├── Dockerfile             # Lambda container image
│   ├── lambda_handler.py      # Lambda entry point
│   └── requirements.txt       # Python dependencies
├── frontend/                   # React frontend
│   └── storybook-ui/          # Vite + React + NextUI app
├── terraform/                  # Modular Terraform configuration
│   ├── envs/
│   │   ├── dev/               # Development environment
│   │   └── prod/              # Production environment
│   └── modules/
│       ├── auth/              # Cognito resources
│       ├── compute/           # Lambda + API Gateway
│       ├── database/          # DocumentDB cluster
│       ├── hosting/           # CloudFront + Route53
│       ├── networking/        # VPC, subnets, NAT
│       └── storage/           # S3 buckets
├── dev-docs/                   # Development documentation
│   ├── DEPLOYMENT_GUIDE.md
│   └── USER_STORIES.md
└── MONGODB_MIGRATION_SUMMARY.md # Database migration details
```
