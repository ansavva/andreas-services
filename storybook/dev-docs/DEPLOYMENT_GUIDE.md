# Storybook Deployment Guide

This guide walks you through deploying Storybook to AWS with separate development and production environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Overview](#environment-overview)
3. [One-Time Setup](#one-time-setup)
4. [Development Environment](#development-environment)
5. [Production Environment](#production-environment)
6. [Verification](#verification)
7. [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Tools

- **AWS CLI** - `brew install awscli`
- **Terraform** >= 1.0 - `brew install terraform`
- **Docker** with buildx - `brew install docker`
- **Node.js** 18+ - `brew install node`
- **Python** 3.12 - `brew install python@3.12`
- **Git** - Should already be installed

### Required AWS Setup

- AWS account with admin access
- AWS CLI configured (`aws configure`)
- Route53 hosted zone for `andreas.services` (already exists)

### Required Secrets

Before starting, gather these values:
- Replicate API token

**Note**: AWS credentials are handled automatically via IAM roles (no access keys needed).

## Environment Overview

Storybook uses two separate environments:

### Development Environment
- **Purpose**: Local development only (no hosting)
- **Resources**: Cognito User Pool + S3 bucket
- **Frontend**: Runs locally at `localhost:5173`
- **Backend**: Runs locally at `localhost:5000`
- **Auth**: Dev Cognito pool (separate users from production)
- **Storage**: Dev S3 bucket (separate data from production)

### Production Environment
- **Purpose**: Live application
- **Resources**: Full stack (Cognito, S3, Lambda, API Gateway, CloudFront, Route53)
- **Frontend**: Hosted at `https://storybook.andreas.services/app`
- **Backend**: Hosted at `https://storybook.andreas.services/api`
- **Auth**: Production Cognito pool
- **Storage**: Production S3 bucket

## One-Time Setup

### 1. Complete Generic AWS Setup

Before deploying Storybook, complete the generic AWS setup for the andreas-services repository:

**Follow the instructions in [dev-docs/AWS_SETUP.md](../../dev-docs/AWS_SETUP.md) at the repository root.**

This one-time setup includes:
- Creating the Terraform state S3 bucket
- Setting up the GitHub Actions IAM role (used by all projects)
- Configuring GitHub repository secrets

### 2. Configure Terraform Variables

Create a local `terraform.tfvars` file with your secrets:

```bash
cd storybook/infra
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your actual values:

```hcl
replicate_api_token = "r8_your_actual_token"
```

**Note**: AWS credentials are handled automatically via IAM roles (Lambda) and AWS CLI (local development). No access keys needed!

**Important**: Never commit `terraform.tfvars` - it's in `.gitignore`.

## Development Environment

The development environment is for local development only. It creates minimal AWS resources (Cognito + S3) that your local frontend and backend connect to.

### Step 1: Deploy Development Infrastructure

```bash
cd storybook/infra
terraform init
terraform plan -var-file=terraform.dev.tfvars
terraform apply -var-file=terraform.dev.tfvars
```

Type `yes` when prompted. This creates:
- Cognito User Pool for dev users
- S3 bucket for dev file storage

### Step 2: Get Development Outputs

```bash
terraform output
```

You'll see:
- `cognito_user_pool_id` - Copy this
- `cognito_user_pool_client_id` - Copy this
- `cognito_domain` - Copy this
- `s3_backend_bucket` - Copy this

### Step 3: Configure Local Backend

```bash
cd storybook/backend
cp .env.example .env
```

Edit `.env` with the Terraform outputs from Step 2:

```bash
S3_BUCKET_NAME=storybook-backend-files-development
AWS_COGNITO_REGION=us-east-1
AWS_COGNITO_USER_POOL_ID=<from terraform output>
AWS_COGNITO_APP_CLIENT_ID=<from terraform output>
REPLICATE_API_TOKEN=<your replicate token>
FLASK_ENV=development
APP_URL=http://localhost:5173
```

### Step 4: Configure Local Frontend

```bash
cd storybook/frontend/storybook-ui
cp .env.local.example .env.local
```

Edit `.env.local` with the Terraform outputs from Step 2:

```bash
VITE_API_URL=http://localhost:5000
VITE_AWS_COGNITO_REGION=us-east-1
VITE_AWS_COGNITO_USER_POOL_ID=<from terraform output>
VITE_AWS_COGNITO_APP_CLIENT_ID=<from terraform output>
VITE_AWS_COGNITO_DOMAIN=<from terraform output>
```

### Step 5: Run Locally

**Terminal 1 - Backend:**
```bash
cd storybook/backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python src/app.py
```

**Terminal 2 - Frontend:**
```bash
cd storybook/frontend/storybook-ui
npm install
npm run dev
```

Visit `http://localhost:5173` - you should be able to sign up/login using the dev Cognito pool!

## Production Environment

The production environment is fully hosted on AWS with CloudFront CDN.

### Infrastructure Deployment

### Step 1: Plan Production Infrastructure

Review what will be created:

```bash
cd storybook/infra
terraform plan -var-file=terraform.prod.tfvars
```

This will show:
- Cognito User Pool and Client (production)
- S3 buckets (frontend and backend files)
- CloudFront distribution
- Lambda function and API Gateway
- Route53 DNS records
- ACM certificates

### Step 2: Apply Production Infrastructure

```bash
terraform apply -var-file=terraform.prod.tfvars
```

Type `yes` when prompted. This will take 10-15 minutes due to:
- Certificate validation (5-10 min)
- CloudFront distribution creation (5-10 min)

### Step 3: Save Outputs

```bash
terraform output > outputs-prod.txt
```

You'll need these values for GitHub Actions secrets.

## Application Deployment (Production Only)

### Option A: Automatic (GitHub Actions)

1. **Create GitHub Environment**

Go to your repository settings → Environments → New environment

Create an environment named: `storybook-production`

2. **Add Environment Secrets**

In the `storybook-production` environment, add these secrets:
```
VITE_API_URL=https://storybook.andreas.services/api
VITE_AWS_COGNITO_REGION=us-east-1
VITE_AWS_COGNITO_USER_POOL_ID=<from terraform output>
VITE_AWS_COGNITO_APP_CLIENT_ID=<from terraform output>
VITE_AWS_COGNITO_DOMAIN=<from terraform output>
```

**Note**: `AWS_ROLE_ARN` should already be set as a repository-level secret from the generic AWS setup.

See [dev-docs/ENVIRONMENTS.md](../../dev-docs/ENVIRONMENTS.md) for more details on how environments work.

3. **Push to Main Branch**

```bash
git add .
git commit -m "Initial Storybook deployment"
git push origin main
```

GitHub Actions will automatically:
- Build backend Docker image
- Push to ECR
- Update Lambda function
- Build frontend
- Deploy to S3
- Invalidate CloudFront cache

## Verification

### 1. Check Infrastructure

```bash
# Verify Lambda function
aws lambda get-function --function-name storybook-backend-production

# Verify S3 buckets
aws s3 ls | grep storybook

# Verify CloudFront distribution
aws cloudfront list-distributions | grep storybook

# Verify Cognito
aws cognito-idp list-user-pools --max-results 10 | grep storybook
```

### 2. Test Endpoints

```bash
# Test backend health
curl https://storybook.andreas.services/api/health

# Test frontend (should return HTML)
curl https://storybook.andreas.services/app
```

### 3. Test Authentication

1. Visit https://storybook.andreas.services/app
2. Click "Login"
3. You should be redirected to Cognito hosted UI
4. Sign up or log in with the admin user you created
5. You should be redirected back to the app, authenticated

## Updating the Application

### Development Environment Updates

Simply restart your local backend and frontend servers after making code changes.

### Production Environment Updates

**Backend Updates**: Changes to `storybook/backend/**` trigger automatic deployment via GitHub Actions.

**Frontend Updates**: Changes to `storybook/frontend/**` trigger automatic deployment via GitHub Actions.

**Infrastructure Updates**:
```bash
cd infra
terraform plan -var-file=terraform.prod.tfvars
terraform apply -var-file=terraform.prod.tfvars
```

## Switching Between Environments

### Switching to Development

```bash
cd storybook/infra
terraform workspace select default  # or create: terraform workspace new development
terraform apply -var-file=terraform.dev.tfvars
```

### Switching to Production

```bash
cd storybook/infra
terraform workspace select default  # or create: terraform workspace new production
terraform apply -var-file=terraform.prod.tfvars
```

## Cleanup

### Destroy Development Environment

```bash
cd storybook/infra
terraform destroy -var-file=terraform.dev.tfvars
```

This removes:
- Development Cognito User Pool
- Development S3 bucket

### Destroy Production Environment

```bash
cd storybook/infra
terraform destroy -var-file=terraform.prod.tfvars
```

This removes all production infrastructure including CloudFront, Lambda, etc.

## Support

For issues:
1. Check the logs: `aws logs tail /aws/lambda/storybook-backend-production --follow`
2. Review GitHub Actions output
3. Check Terraform state: `terraform show`
4. Consult [infra/README.md](infra/README.md) for detailed infrastructure docs
