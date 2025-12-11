# GitHub Environments Guide

This repository uses GitHub Environments to manage project-specific secrets and configurations.

## Why Environments?

Since multiple projects (storybook, humbugg, etc.) share the same repository, we use environments to:
- Isolate project-specific secrets (e.g., each project has its own Cognito configuration)
- Share common secrets at the repository level (e.g., `AWS_ROLE_ARN`)
- Prevent conflicts between projects

## Repository-Level Secrets (Shared)

These secrets are available to all workflows:

| Secret Name | Description | Set in |
|-------------|-------------|--------|
| `AWS_ROLE_ARN` | IAM role ARN for GitHub Actions | Repository Settings → Secrets |

## Environment-Specific Secrets

Each project has its own environment with project-specific secrets:

### storybook-production

| Secret Name | Description | Example Value |
|-------------|-------------|---------------|
| `VITE_API_URL` | Storybook API URL | `https://storybook.andreas.services/api` |
| `VITE_AWS_COGNITO_REGION` | AWS region for Cognito | `us-east-1` |
| `VITE_AWS_COGNITO_USER_POOL_ID` | Storybook Cognito User Pool ID | `us-east-1_ABC123` |
| `VITE_AWS_COGNITO_APP_CLIENT_ID` | Storybook Cognito App Client ID | `1a2b3c4d5e6f7g8h9i` |
| `VITE_AWS_COGNITO_DOMAIN` | Storybook Cognito domain | `storybook-auth-prod.auth.us-east-1.amazoncognito.com` |

### humbugg-production (Future)

When you deploy humbugg, create a `humbugg-production` environment with:
- `VITE_API_URL` (humbugg's API URL)
- `VITE_AWS_COGNITO_USER_POOL_ID` (humbugg's Cognito pool)
- etc.

## How to Create an Environment

1. Go to your GitHub repository
2. Click **Settings** → **Environments**
3. Click **New environment**
4. Enter the environment name (e.g., `storybook-production`)
5. Click **Configure environment**
6. Under **Environment secrets**, click **Add secret**
7. Add each secret with its name and value

## How Workflows Use Environments

In workflow files, specify the environment:

```yaml
jobs:
  deploy-frontend:
    runs-on: ubuntu-latest
    environment: storybook-production  # This loads secrets from the environment
    steps:
      - name: Build frontend
        env:
          VITE_API_URL: ${{ secrets.VITE_API_URL }}  # From storybook-production environment
```

## Benefits

1. **No Conflicts**: Each project has its own Cognito configuration without naming conflicts
2. **Clear Separation**: Easy to see which secrets belong to which project
3. **Security**: Secrets are scoped to specific environments
4. **Reusability**: Common secrets like `AWS_ROLE_ARN` are shared across all projects

## Adding a New Project

When adding a new project (e.g., `myapp`):

1. Create a new environment: `myapp-production`
2. Add project-specific secrets to that environment
3. Update the workflow file to use `environment: myapp-production`
4. The shared `AWS_ROLE_ARN` is automatically available

No changes needed to the generic IAM role or repository-level configuration!
