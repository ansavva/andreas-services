# Storybook Deployment Guide

This guide walks you through deploying Storybook to AWS from scratch.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [One-Time Setup](#one-time-setup)
3. [Infrastructure Deployment](#infrastructure-deployment)
4. [Application Deployment](#application-deployment)
5. [Verification](#verification)
6. [Troubleshooting](#troubleshooting)

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
- AWS access keys for S3 operations (optional if using IAM roles)

## One-Time Setup

### 1. Complete Generic AWS Setup

Before deploying Storybook, complete the generic AWS setup for the andreas-services repository:

**Follow the instructions in [dev-docs/AWS_SETUP.md](../../dev-docs/AWS_SETUP.md) at the repository root.**

This one-time setup includes:
- Creating the Terraform state S3 bucket
- Setting up the GitHub Actions IAM role (used by all projects)
- Configuring GitHub repository secrets

### 2. Configure Terraform Variables

```bash
cd storybook/infra
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your actual values:

```hcl
replicate_api_token    = "r8_your_actual_token"
aws_access_key_id      = "AKIA..." # Optional
aws_secret_access_key  = "your_secret" # Optional
```

**Important**: Never commit `terraform.tfvars` - it's in `.gitignore`.

## Infrastructure Deployment

### Step 1: Initialize Terraform

```bash
cd storybook/infra
terraform init
```

### Step 2: Plan Infrastructure

Review what will be created:

```bash
terraform plan
```

This will show:
- Cognito User Pool and Client
- S3 buckets (frontend and backend files)
- CloudFront distribution
- Lambda function and API Gateway
- Route53 DNS records
- ACM certificates

### Step 3: Apply Infrastructure

```bash
terraform apply
```

Type `yes` when prompted. This will take 10-15 minutes due to:
- Certificate validation (5-10 min)
- CloudFront distribution creation (5-10 min)

### Step 4: Save Outputs

```bash
terraform output > outputs.txt
```

You'll need these values for:
- GitHub Actions secrets
- Local development
- Frontend configuration

## Application Deployment

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

### Backend Updates

Changes to `storybook/backend/**` trigger automatic deployment via GitHub Actions.

### Frontend Updates

Changes to `storybook/frontend/**` trigger automatic deployment via GitHub Actions.

### Infrastructure Updates

```bash
cd infra
terraform plan
terraform apply
```

## Cleanup

To destroy all infrastructure:

```bash
cd infra
terraform destroy
```

## Support

For issues:
1. Check the logs: `aws logs tail /aws/lambda/storybook-backend-production --follow`
2. Review GitHub Actions output
3. Check Terraform state: `terraform show`
4. Consult [infra/README.md](infra/README.md) for detailed infrastructure docs
