# Migration Guide: From infra/ to terraform/

This guide helps you migrate from the old single-root approach (`storybook/infra/`) to the new multi-root modular approach (`storybook/terraform/`).

## Why Migrate?

### Old Approach Problems
```hcl
# infra/lambda.tf
resource "aws_lambda_function" "backend" {
  count = var.environment == "production" ? 1 : 0  # ❌ Conditionals everywhere
  function_name = "storybook-backend-${var.environment}"
  role = aws_iam_role.lambda[0].arn  # ❌ Must use [0] everywhere
  # ...
}
```

### New Approach Benefits
```hcl
# terraform/modules/compute/main.tf
resource "aws_lambda_function" "backend" {
  # ✅ No conditionals - module is only called in prod
  function_name = "${var.project}-backend-${var.environment}"
  role = aws_iam_role.lambda.arn  # ✅ Clean references
  # ...
}

# terraform/envs/prod/main.tf
module "compute" {  # ✅ Only called in prod environment
  source = "../../modules/compute"
  # ...
}
```

## Migration Steps

### Step 1: Test Development Environment

```bash
cd /Users/andreassavva/Repos/andreas-services/storybook/terraform/envs/dev
terraform init
terraform plan
```

Review the plan - it should show:
- 1 Cognito User Pool
- 1 Cognito User Pool Client
- 1 Cognito User Pool Domain
- 1 S3 bucket (backend files)
- No Lambda, API Gateway, CloudFront, or Route53

If it looks good:
```bash
terraform apply
terraform output
```

### Step 2: Update Local .env Files

Use the outputs from Step 1:

**Backend `.env`:**
```bash
cd ../../backend
cp .env.example .env
# Edit with terraform outputs
```

**Frontend `.env.local`:**
```bash
cd ../frontend/storybook-ui
cp .env.local.example .env.local
# Edit with terraform outputs
```

### Step 3: Test Locally

```bash
# Terminal 1
cd storybook/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m src.app

# Terminal 2
cd storybook/frontend/storybook-ui
npm install
npm run dev
```

Visit http://localhost:5173 and test authentication.

### Step 4: Plan Production (Don't Apply Yet!)

```bash
cd /Users/andreassavva/Repos/andreas-services/storybook/terraform/envs/prod

# Create local terraform.tfvars with secrets
echo 'replicate_api_token = "r8_YOUR_TOKEN"' > terraform.tfvars

terraform init
terraform plan
```

Review carefully - it should show:
- Everything from dev, plus:
- Lambda function + ECR
- API Gateway
- CloudFront distribution
- Route53 records
- ACM certificate

**DO NOT APPLY YET** - this will create duplicate resources!

### Step 5: State Migration (CAREFUL!)

You have two options:

#### Option A: Start Fresh (Recommended if dev worked)

This is safer but requires downtime:

1. **Backup current state:**
   ```bash
   cd /Users/andreassavva/Repos/andreas-services/storybook/infra
   terraform state pull > backup-$(date +%Y%m%d).json
   ```

2. **Destroy old production** (DOWNTIME WARNING):
   ```bash
   terraform destroy -var-file=terraform.prod.tfvars
   ```

3. **Deploy new production:**
   ```bash
   cd ../terraform/envs/prod
   terraform apply
   ```

4. **Update GitHub Actions secrets** with new outputs

5. **Deploy application** via GitHub Actions

#### Option B: Import Resources (No Downtime, Complex)

This is more complex but avoids downtime. You'll need to import existing resources into the new state:

```bash
cd /Users/andreassavva/Repos/andreas-services/storybook/terraform/envs/prod
terraform init

# Import existing resources (example)
terraform import module.auth.aws_cognito_user_pool.main storybook-production
terraform import module.storage.aws_s3_bucket.backend_files storybook-backend-files-production
# ... repeat for all resources

terraform plan  # Should show "No changes"
```

**Note**: This is error-prone. Only use if you can't afford downtime.

### Step 6: Update GitHub Actions (if using Option A)

After new production is deployed:

```bash
cd ../envs/prod
terraform output
```

Update GitHub Actions secrets in repository settings:
- `VITE_AWS_COGNITO_USER_POOL_ID`
- `VITE_AWS_COGNITO_APP_CLIENT_ID`
- `VITE_AWS_COGNITO_DOMAIN`

### Step 7: Archive Old infra/ Directory

After confirming everything works:

```bash
cd /Users/andreassavva/Repos/andreas-services/storybook
mv infra infra.old
git add terraform/
git commit -m "Migrate to modular Terraform structure"
```

## Rollback Plan

If something goes wrong:

### If using Option A (destroyed old infra):
```bash
cd storybook/infra.old
terraform init
terraform apply -var-file=terraform.prod.tfvars
```

### If using Option B (imported):
```bash
# Remove new state
cd terraform/envs/prod
rm -rf .terraform terraform.tfstate*

# Old infra still works
cd ../../infra
terraform plan
```

## Verification Checklist

After migration:

- [ ] Dev Cognito pool created
- [ ] Dev S3 bucket created
- [ ] Local backend connects to dev resources
- [ ] Local frontend auth works
- [ ] Prod infrastructure deployed
- [ ] Application accessible at https://storybook.andreas.services
- [ ] GitHub Actions deployment works
- [ ] Old infra/ directory archived

## Troubleshooting

### "Module not found"
Ensure you're in the correct directory:
```bash
pwd  # Should be .../terraform/envs/{dev|prod}
```

### "State lock" errors
```bash
# If safe to do so:
terraform force-unlock LOCK_ID
```

### "Resource already exists"
You might be trying to create resources that already exist. Use Option B (import) instead.

## Getting Help

- Review module source in `terraform/modules/`
- Check environment config in `terraform/envs/{dev|prod}/`
- Compare with old config in `infra/` (before archiving)
- Read main README: `terraform/README.md`
