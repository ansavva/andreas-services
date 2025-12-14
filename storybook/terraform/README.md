# Storybook Terraform Infrastructure

Clean multi-environment Terraform configuration using reusable modules and separate environment roots.

## Directory Structure

```
terraform/
├── modules/              # Reusable modules
│   ├── auth/            # Cognito authentication
│   ├── storage/         # S3 buckets
│   ├── compute/         # Lambda + API Gateway
│   └── hosting/         # CloudFront + Route53 (references root cert)
└── envs/                # Environment-specific roots
    ├── dev/             # Development (Cognito + S3 only)
    └── prod/            # Production (full stack)
```

## Dependencies

### Root Infrastructure

Storybook depends on **root-level cross-cutting infrastructure** managed at `/terraform/`:

- **Route53 Hosted Zone**: `andreas.services`
- **ACM Certificate**: `*.andreas.services` wildcard cert

**Important**: Deploy root infrastructure first:
```bash
cd /Users/andreassavva/Repos/andreas-services/terraform
terraform init
terraform apply
```

See [root terraform README](../../terraform/README.md) for details.

## Environments

### Development
- **Purpose**: Local development only
- **Resources**: Cognito User Pool + S3 bucket
- **State**: `s3://andreas-services-terraform-state/storybook/dev/terraform.tfstate`
- **Frontend**: localhost:5173
- **Backend**: localhost:5000

### Production
- **Purpose**: Live hosted application
- **Resources**: Full stack (Cognito, S3, Lambda, API Gateway, CloudFront, Route53)
- **State**: `s3://andreas-services-terraform-state/storybook/prod/terraform.tfstate`
- **URL**: https://storybook.andreas.services

## Key Benefits Over Single-Root Approach

### Before (old infra/ directory)
- ❌ Conditionals everywhere (`count = var.environment == "production" ? 1 : 0`)
- ❌ Must use `[0]` array index on every resource reference
- ❌ Single state file for both environments
- ❌ Easy to accidentally deploy wrong environment
- ❌ Complex variable management

### After (this terraform/ directory)
- ✅ Clean module calls, no conditionals
- ✅ Separate state files (impossible to mix environments)
- ✅ Must explicitly `cd` into environment directory
- ✅ Simple, flat variable files per environment
- ✅ Clear module boundaries and reuse

## Quick Start

### Deploy Development

```bash
cd envs/dev
terraform init
terraform plan
terraform apply
terraform output  # Copy values to local .env files
```

### Deploy Production

```bash
cd envs/prod

# Create local terraform.tfvars (git-ignored) with secrets
echo 'replicate_api_token = "r8_your_token"' > terraform.tfvars

terraform init
terraform plan
terraform apply
terraform output  # Use for GitHub Actions secrets
```

## Module Reuse Examples

### Auth Module (both envs)
```hcl
# Dev
module "auth" {
  callback_urls = ["http://localhost:5173"]
}

# Prod
module "auth" {
  callback_urls = ["https://storybook.andreas.services/app"]
}
```

### Storage Module (different configs)
```hcl
# Dev
module "storage" {
  create_frontend_bucket = false  # No hosting needed
}

# Prod
module "storage" {
  create_frontend_bucket = true   # Need frontend hosting
}
```

### Compute Module (prod only)
```hcl
# Dev - not included (runs locally)

# Prod
module "compute" {
  # Uses outputs from other modules
  cognito_user_pool_id = module.auth.user_pool_id
  s3_bucket_arn        = module.storage.backend_files_bucket_arn
}
```

## Passing Outputs Between Modules

```hcl
# Storage module output
output "backend_files_bucket_arn" {
  value = aws_s3_bucket.backend_files.arn
}

# Compute module uses it
module "compute" {
  s3_bucket_arn = module.storage.backend_files_bucket_arn
}
```

## Safety Mechanisms

### 1. Separate State Files
- Dev: `storybook/dev/terraform.tfstate`
- Prod: `storybook/prod/terraform.tfstate`
- **Impossible to accidentally affect prod from dev directory**

### 2. Directory-Based Isolation
- Must explicitly `cd` into environment directory
- No global apply from root
- Clear visual separation

### 3. AWS Profile Separation (recommended)
```bash
# ~/.aws/config
[profile dev]
role_arn = arn:aws:iam::ACCOUNT:role/dev-role

[profile prod]
role_arn = arn:aws:iam::ACCOUNT:role/prod-role

# Use different profiles
cd envs/dev && terraform apply                    # Uses default/dev
cd envs/prod && AWS_PROFILE=prod terraform apply  # Requires explicit prod
```

## Migration from Old infra/ Directory

The old `storybook/infra/` directory used a single root with conditionals. This new structure is cleaner:

1. **Old approach**: Single root + `var.environment` + `count` conditionals
2. **New approach**: Separate roots + reusable modules

To migrate:
1. Keep the old `infra/` directory until ready to switch
2. Deploy new `terraform/envs/dev` first to test
3. Compare outputs to ensure parity
4. When ready, migrate production state carefully
5. Archive old `infra/` directory

## Common Commands

### Initialize Environment
```bash
cd envs/{dev|prod}
terraform init
```

### Plan Changes
```bash
terraform plan
```

### Apply Changes
```bash
terraform apply
```

### View Outputs
```bash
terraform output
```

### Destroy Environment
```bash
terraform destroy
```

## Naming Conventions

All resources use consistent naming:
```hcl
# Dev resources
storybook-development (Cognito pool)
storybook-backend-files-development (S3 bucket)

# Prod resources
storybook-production (Cognito pool)
storybook-backend-files-production (S3 bucket)
storybook-backend-production (Lambda function)
```

Tags are automatically applied:
```hcl
{
  Project     = "storybook"
  Environment = "development" # or "production"
  ManagedBy   = "Terraform"
  Region      = "us-east-1"
}
```

## Troubleshooting

### Module not found
Make sure you're running from an environment directory:
```bash
cd envs/dev  # or envs/prod
terraform init
```

### State conflicts
Each environment has separate state - ensure you're in the correct directory.

### Provider version conflicts
Lock files are per-environment. Run `terraform init -upgrade` if needed.

## Next Steps

After deploying dev:
1. Run `terraform output`
2. Copy Cognito values to local `.env` files
3. Start local backend and frontend
4. Test authentication against dev Cognito pool

After deploying prod:
1. Run `terraform output`
2. Add outputs to GitHub Actions secrets
3. Push to main branch to trigger deployment
4. Verify application at https://storybook.andreas.services

## Support

- Module documentation: See individual module README files (if created)
- Old deployment guide: `../dev-docs/DEPLOYMENT_GUIDE.md`
- Infrastructure docs: `../infra/README.md`
