# Terraform Architecture

This document explains the terraform structure across the andreas-services monorepo.

## Overview

The monorepo uses a **two-level terraform structure**:

1. **Root Level** (`/terraform/`) - Cross-cutting infrastructure
2. **Service Level** (`/storybook/terraform/`, `/humbugg/terraform/`) - Service-specific infrastructure

## Architecture Diagram

```
andreas-services/
├── terraform/                           # ROOT LEVEL
│   ├── main.tf                         # Route53 zone + ACM cert
│   ├── outputs.tf                      # Shared outputs
│   └── backend.tf                      # State: root/terraform.tfstate
│
├── storybook/
│   └── terraform/                       # SERVICE LEVEL
│       ├── modules/
│       │   ├── auth/                   # Cognito (service-specific)
│       │   ├── storage/                # S3 (service-specific)
│       │   ├── compute/                # Lambda (service-specific)
│       │   └── hosting/                # CloudFront (uses root cert)
│       └── envs/
│           ├── dev/                    # Dev environment
│           └── prod/                   # Prod environment
│
└── humbugg/
    └── terraform/                       # SERVICE LEVEL (future)
        └── ...                         # Same pattern as storybook
```

## Root-Level Infrastructure

**Location**: `/terraform/`

**Manages**: Cross-cutting resources shared by ALL services

**Resources**:
- Route53 Hosted Zone for `andreas.services`
- ACM Wildcard Certificate for `*.andreas.services`

**State**: `s3://andreas-services-terraform-state/root/terraform.tfstate`

**Why?**
- Single SSL certificate for all subdomains (storybook, humbugg, etc.)
- Shared DNS zone - each service creates its own records
- Prevents hitting ACM limits (20 certs per account)
- Services can be destroyed without breaking others

**Deploy Once**: This infrastructure is deployed once and rarely changes.

```bash
cd terraform/
terraform init
terraform apply
```

## Service-Level Infrastructure

**Location**: `/storybook/terraform/`, `/humbugg/terraform/`, etc.

**Manages**: Service-specific resources

**Resources**:
- Cognito User Pool (per service, per environment)
- S3 buckets (per service)
- Lambda functions (per service)
- CloudFront distributions (per service, uses shared cert)
- Route53 records (per service, in shared zone)

**Pattern**: Each service follows the same structure:
```
{service}/terraform/
├── modules/          # Reusable modules
└── envs/            # Environment roots
    ├── dev/         # Development
    └── prod/        # Production
```

**State**: Separate file per service per environment
```
s3://andreas-services-terraform-state/
├── root/terraform.tfstate
├── storybook/dev/terraform.tfstate
├── storybook/prod/terraform.tfstate
├── humbugg/dev/terraform.tfstate
└── humbugg/prod/terraform.tfstate
```

## How Services Reference Root Infrastructure

Services use Terraform **data sources** to reference root infrastructure:

```hcl
# In storybook/terraform/modules/hosting/main.tf

# Get the shared ACM certificate
data "aws_acm_certificate" "wildcard" {
  provider = aws.us_east_1
  domain   = "*.andreas.services"
  statuses = ["ISSUED"]
}

# Get the shared Route53 zone
data "aws_route53_zone" "main" {
  name = "andreas.services"
}

# Use them
resource "aws_cloudfront_distribution" "app" {
  viewer_certificate {
    acm_certificate_arn = data.aws_acm_certificate.wildcard.arn
  }
}

resource "aws_route53_record" "app" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "storybook.andreas.services"
  # ...
}
```

## Deployment Order

### First Time (New Monorepo)

1. **Deploy root infrastructure** (once)
   ```bash
   cd terraform/
   terraform init && terraform apply
   ```

2. **Deploy service infrastructure** (per service)
   ```bash
   cd storybook/terraform/envs/dev
   terraform init && terraform apply
   ```

### Day-to-Day (Existing Monorepo)

Root infrastructure rarely changes. You'll mostly work with service-level terraform:

```bash
cd storybook/terraform/envs/dev
terraform plan
terraform apply
```

## Benefits

### ✅ Clear Separation of Concerns
- Cross-cutting resources in one place
- Service resources isolated
- No confusion about what affects what

### ✅ Independent Service Lifecycles
- Deploy/destroy services independently
- Destroying storybook doesn't break humbugg
- Each service has its own state

### ✅ Resource Efficiency
- Single SSL cert for all services (not 20+)
- Single DNS zone (not one per service)
- Shared resources truly shared

### ✅ Scalability
- Easy to add new services
- Just copy the service-level pattern
- Root infrastructure already supports it

### ✅ Safety
- Can't accidentally destroy cross-cutting resources
- Separate state files prevent conflicts
- Must explicitly `cd` into environment

## State Management

All state files are stored in S3:

| State File | Contains | Managed By |
|------------|----------|------------|
| `root/terraform.tfstate` | Route53 zone, ACM cert | Root terraform |
| `storybook/dev/terraform.tfstate` | Storybook dev resources | Storybook dev |
| `storybook/prod/terraform.tfstate` | Storybook prod resources | Storybook prod |
| `humbugg/prod/terraform.tfstate` | Humbugg prod resources | Humbugg prod |

**Key Point**: Each is completely independent. You can destroy `storybook/dev` without affecting `storybook/prod` or root infrastructure.

## Adding a New Service

To add a new service (e.g., `humbugg`):

1. **No changes to root terraform** - it already supports all subdomains

2. **Copy the service-level pattern**:
   ```bash
   cp -r storybook/terraform humbugg/terraform
   ```

3. **Update service-specific values** in the new terraform

4. **Deploy**:
   ```bash
   cd humbugg/terraform/envs/prod
   terraform init
   terraform apply
   ```

The service will automatically use the shared Route53 zone and ACM certificate.

## Destruction Safety

### Safe to Destroy
✅ Individual service environments:
```bash
cd storybook/terraform/envs/dev
terraform destroy  # Only affects storybook dev
```

### ⚠️ Dangerous to Destroy
Root infrastructure:
```bash
cd terraform/
terraform destroy  # BREAKS ALL SERVICES - don't do this!
```

Only destroy root infrastructure if you're tearing down the entire monorepo.

## Documentation

- **Root terraform**: See `/terraform/README.md`
- **Storybook terraform**: See `/storybook/terraform/README.md`
- **Quick start**: See `/storybook/terraform/QUICKSTART.md`
- **Migration guide**: See `/storybook/terraform/MIGRATION.md`

## Questions?

- What is cross-cutting vs service-specific? See "Root vs Service Level" above
- How do I add a new service? See "Adding a New Service" above
- How do I deploy? See "Deployment Order" above
- Why this structure? See "Benefits" above
