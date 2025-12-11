# Storybook Infrastructure

This directory contains Terraform configuration for deploying the Storybook application infrastructure on AWS.

## Architecture Overview

- **Frontend**: S3 + CloudFront serving static React app at `storybook.andreas.services/app`
- **Backend**: Lambda function (containerized Flask API) at `api.storybook.andreas.services`
- **Authentication**: AWS Cognito User Pool
- **Storage**: S3 bucket for user uploads and project data
- **DNS**: Route53 records in the `andreas.services` hosted zone

## Prerequisites

1. **AWS CLI** configured with appropriate credentials
2. **Terraform** >= 1.0
3. **S3 bucket** for Terraform state: `andreas-services-terraform-state`
4. **Route53 hosted zone** for `andreas.services`
5. **GitHub OIDC provider** configured in AWS for GitHub Actions

## Initial Setup

### 1. Create Terraform State Bucket (one-time)

```bash
aws s3 mb s3://andreas-services-terraform-state --region us-east-1
aws s3api put-bucket-versioning \
  --bucket andreas-services-terraform-state \
  --versioning-configuration Status=Enabled
```

### 2. Configure Variables

Copy the example variables file and fill in your values:

```bash
cd storybook/infra
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your actual values
```

### 3. Initialize Terraform

```bash
terraform init
```

### 4. Review and Apply

```bash
terraform plan
terraform apply
```

### 5. Get Outputs

After applying, get the important values:

```bash
terraform output
```

Save these outputs - you'll need them for:
- GitHub Actions secrets
- Frontend environment variables
- Backend environment variables

## GitHub Actions Setup

### Required Secrets

Add these secrets to your GitHub repository (`Settings > Secrets and variables > Actions`):

**AWS Authentication:**
- `AWS_ROLE_ARN`: ARN of the IAM role for GitHub Actions (format: `arn:aws:iam::ACCOUNT_ID:role/github-actions-role`)

**Frontend Environment Variables:**
- `VITE_API_URL`: `https://api.storybook.andreas.services`
- `VITE_AWS_COGNITO_REGION`: From `terraform output cognito_user_pool_id`
- `VITE_AWS_COGNITO_USER_POOL_ID`: From `terraform output cognito_user_pool_id`
- `VITE_AWS_COGNITO_APP_CLIENT_ID`: From `terraform output cognito_user_pool_client_id`
- `VITE_AWS_COGNITO_DOMAIN`: From `terraform output cognito_domain`

### Creating GitHub OIDC Provider (one-time)

If not already set up, create an OIDC provider for GitHub Actions:

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

Then create an IAM role that trusts GitHub Actions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:USERNAME/andreas-services:*"
        }
      }
    }
  ]
}
```

Attach policies for ECR, Lambda, S3, and CloudFront access to this role.

## Deployment

The application deploys automatically via GitHub Actions when you push to the `main` branch with changes in the `storybook/` directory.

### Manual Deployment

**Backend:**
```bash
cd storybook/backend
docker buildx build --platform linux/amd64 -t ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/storybook-backend-production:latest .
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/storybook-backend-production:latest
aws lambda update-function-code --function-name storybook-backend-production --image-uri ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/storybook-backend-production:latest
```

**Frontend:**
```bash
cd storybook/frontend/storybook-ui
npm install
npm run build
aws s3 sync dist/ s3://storybook-frontend-production --delete
aws cloudfront create-invalidation --distribution-id DISTRIBUTION_ID --paths "/*"
```

## Cognito Configuration

After Terraform creates the Cognito User Pool:

1. **Create an admin user** (optional):
```bash
aws cognito-idp admin-create-user \
  --user-pool-id $(terraform output -raw cognito_user_pool_id) \
  --username admin@example.com \
  --user-attributes Name=email,Value=admin@example.com Name=email_verified,Value=true \
  --temporary-password TempPassword123! \
  --message-action SUPPRESS
```

2. **Test authentication** by visiting the frontend and signing up/logging in

## Useful Commands

```bash
# View current infrastructure
terraform show

# Destroy infrastructure (CAUTION!)
terraform destroy

# Update specific resource
terraform apply -target=aws_lambda_function.backend

# View Cognito users
aws cognito-idp list-users --user-pool-id $(terraform output -raw cognito_user_pool_id)

# View Lambda logs
aws logs tail /aws/lambda/storybook-backend-production --follow

# Invalidate CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id $(terraform output -raw cloudfront_distribution_id) \
  --paths "/*"
```

## Troubleshooting

### Lambda Function Not Updating
- Check ECR image exists: `aws ecr describe-images --repository-name storybook-backend-production`
- Check Lambda logs: `aws logs tail /aws/lambda/storybook-backend-production --follow`
- Verify environment variables are set correctly

### Frontend Not Loading
- Check S3 bucket contents: `aws s3 ls s3://storybook-frontend-production/`
- Verify CloudFront distribution is enabled
- Check Route53 DNS records are pointing correctly
- Clear CloudFront cache if changes aren't appearing

### Cognito Authentication Issues
- Verify callback URLs match in Cognito User Pool Client settings
- Check CORS settings on API Gateway
- Verify frontend has correct Cognito configuration

## Cost Estimation

Approximate monthly costs (us-east-1, low traffic):
- CloudFront: $1-5
- S3: $0.50-2
- Lambda: $0-5 (free tier: 1M requests/month, 400,000 GB-seconds compute)
- API Gateway: $1-3
- Cognito: $0 (free tier: 50,000 MAUs)
- Route53: $0.50 per hosted zone
- **Total: ~$5-20/month**

## Security Notes

- Never commit `terraform.tfvars` with real secrets
- Use GitHub Actions secrets for sensitive values
- Enable MFA for AWS root account
- Regularly rotate Replicate API tokens
- Review CloudWatch Logs for suspicious activity
- Keep dependencies up to date
