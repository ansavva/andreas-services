# AWS Setup Guide for andreas-services

This guide will help you set up AWS infrastructure for deploying projects in the andreas-services repository.

## Prerequisites

1. AWS account with administrative access
2. AWS CLI installed and configured
3. GitHub repository access
4. Domain (andreas.services) configured in Route53

## Step 1: Configure AWS CLI

If you haven't already configured AWS CLI, run:

```bash
aws configure
```

Enter your:
- AWS Access Key ID
- AWS Secret Access Key
- Default region: `us-east-1`
- Default output format: `json`

Verify your configuration:

```bash
aws sts get-caller-identity
```

## Step 2: Create Terraform State S3 Bucket

Create an S3 bucket to store Terraform state (do this once for all projects):

```bash
aws s3 mb s3://andreas-services-terraform-state --region us-east-1
```

Enable versioning:

```bash
aws s3api put-bucket-versioning \
  --bucket andreas-services-terraform-state \
  --versioning-configuration Status=Enabled
```

Enable encryption:

```bash
aws s3api put-bucket-encryption \
  --bucket andreas-services-terraform-state \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'
```

## Step 3: Set Up GitHub Actions IAM Role

This creates a generic IAM role that can be used by all GitHub Actions workflows in the repository.

### Get Your AWS Account ID

```bash
aws sts get-caller-identity --query Account --output text
```

Save this account ID.

### Update IAM Policies

Edit `.github/iam/github-trust-policy.json`:
- Replace `YOUR_AWS_ACCOUNT_ID` with your account ID
- Replace `YOUR_GITHUB_USERNAME` with your GitHub username/org

### Create OIDC Provider (if needed)

Check if it already exists:

```bash
aws iam list-open-id-connect-providers
```

If you don't see `token.actions.githubusercontent.com`, create it:

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### Create the IAM Role

```bash
aws iam create-role \
  --role-name github-actions-andreas-services \
  --assume-role-policy-document file://.github/iam/github-trust-policy.json \
  --description "Generic role for GitHub Actions in andreas-services repository"
```

### Attach Permissions

```bash
aws iam put-role-policy \
  --role-name github-actions-andreas-services \
  --policy-name GitHubActionsPermissions \
  --policy-document file://.github/iam/github-permissions-policy.json
```

### Get the Role ARN

```bash
aws iam get-role \
  --role-name github-actions-andreas-services \
  --query Role.Arn \
  --output text
```

Save this ARN - you'll add it to GitHub Secrets.

## Step 4: Configure GitHub Repository Secrets

### Repository-Level Secret (Shared by All Projects)

Go to your GitHub repository Settings → Secrets and variables → Actions → Secrets.

Add the following repository secret:

- **Name**: `AWS_ROLE_ARN`
- **Value**: The ARN from Step 3 (e.g., `arn:aws:iam::123456789012:role/github-actions-andreas-services`)

### Project-Specific Secrets Using Environments

Each project (storybook, humbugg, etc.) will have its own GitHub Environment with project-specific secrets.

**You don't need to create environments now** - follow each project's deployment guide for environment-specific setup.

For more information, see [ENVIRONMENTS.md](ENVIRONMENTS.md).

## Project-Specific Setup

After completing the generic AWS setup above, follow the project-specific instructions:

### Storybook

See [storybook/dev-docs/DEPLOYMENT_GUIDE.md](../storybook/dev-docs/DEPLOYMENT_GUIDE.md) for:
- Running Terraform to provision infrastructure
- Setting up Cognito users
- Configuring environment variables
- Deploying the application

### Other Projects

Each project should have its own deployment guide in its respective directory.

## Troubleshooting

### "Unable to locate credentials"

Run `aws configure` and enter your credentials.

### "Access Denied" errors

Make sure your AWS user has the necessary permissions to create IAM roles and S3 buckets.

### GitHub Actions failing

1. Verify `AWS_ROLE_ARN` secret is set correctly in GitHub
2. Check that the IAM role trust policy matches your GitHub username/org
3. Review CloudWatch logs for detailed error messages

## Security Best Practices

1. **Never commit AWS credentials** to the repository
2. **Use OIDC authentication** for GitHub Actions (not access keys)
3. **Enable MFA** on your AWS account
4. **Regularly rotate** access keys used with AWS CLI
5. **Review IAM permissions** periodically to ensure least privilege

## Next Steps

Once AWS is configured, you can:
1. Deploy projects using their respective deployment guides
2. Set up additional GitHub Actions workflows for other projects
3. Monitor deployments in AWS CloudWatch
