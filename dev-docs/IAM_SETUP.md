# GitHub Actions IAM Setup for andreas-services

This directory contains IAM policies for setting up GitHub Actions with AWS OIDC authentication.

## Overview

These policies create a generic IAM role that can be used by **all GitHub Actions workflows** in the andreas-services repository. This allows different projects (storybook, humbugg, etc.) to share the same IAM role while deploying to AWS.

## Files

- `github-trust-policy.json`: Trust policy that allows GitHub Actions to assume the IAM role
- `github-permissions-policy.json`: Permissions policy that grants access to AWS services

## Setup Instructions

Follow these steps to configure the IAM role in AWS:

### Prerequisites

- AWS CLI configured with credentials: `aws configure`
- Your AWS account ID
- Your GitHub username/organization

### Step 1: Get Your AWS Account ID

```bash
aws sts get-caller-identity --query Account --output text
```

Save this account ID for the next steps.

### Step 2: Update the Trust Policy

Edit `github-trust-policy.json` and replace:
- `YOUR_AWS_ACCOUNT_ID` with your actual AWS account ID from Step 1
- `YOUR_GITHUB_USERNAME` with your GitHub username or organization name

### Step 3: Create OIDC Provider (if not already exists)

Check if the OIDC provider already exists:

```bash
aws iam list-open-id-connect-providers
```

If you don't see `token.actions.githubusercontent.com` in the output, create it:

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### Step 4: Create the IAM Role

```bash
aws iam create-role \
  --role-name github-actions-andreas-services \
  --assume-role-policy-document file://.github/iam/github-trust-policy.json \
  --description "Generic role for GitHub Actions in andreas-services repository"
```

### Step 5: Attach the Permissions Policy

```bash
aws iam put-role-policy \
  --role-name github-actions-andreas-services \
  --policy-name GitHubActionsPermissions \
  --policy-document file://.github/iam/github-permissions-policy.json
```

### Step 6: Get the Role ARN

```bash
aws iam get-role \
  --role-name github-actions-andreas-services \
  --query Role.Arn \
  --output text
```

Save this ARN - you'll use it in your GitHub Actions workflows.

## Using the Role in GitHub Actions

In your workflow files (e.g., `.github/workflows/deploy-storybook.yml`), configure AWS credentials like this:

```yaml
- name: Configure AWS credentials
  uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::YOUR_ACCOUNT_ID:role/github-actions-andreas-services
    aws-region: us-east-1
```

Replace `YOUR_ACCOUNT_ID` with your actual AWS account ID.

## Permissions Included

The role has permissions for:
- **ECR**: Push and pull Docker images
- **Lambda**: Update function code and configuration
- **S3**: Upload/download files to frontend and backend buckets
- **CloudFront**: Invalidate cache
- **API Gateway**: Manage API configurations
- **Cognito**: Read user pool configurations
- **Route53**: Read hosted zone information
- **ACM**: Read certificate information

## Security Notes

- The trust policy uses `StringLike` with wildcard to allow any branch/ref in the repository
- Permissions follow the principle of least privilege for deployment tasks
- S3 permissions use naming patterns (`*-frontend-*`, `*-backend-files-*`) to restrict access

## Updating Permissions

If you need to add permissions for a new service:

1. Edit `github-permissions-policy.json`
2. Add the new permissions under a new `Sid`
3. Update the policy in AWS:

```bash
aws iam put-role-policy \
  --role-name github-actions-andreas-services \
  --policy-name GitHubActionsPermissions \
  --policy-document file://.github/iam/github-permissions-policy.json
```
