# Root-Level Infrastructure

This directory manages **cross-cutting infrastructure** shared by all services in the andreas-services monorepo.

## What's Managed Here

### 1. Route53 Hosted Zone
- **Domain**: `andreas.services`
- **Purpose**: DNS zone for all subdomains
- **Used by**: All services (storybook, humbugg, etc.)

### 2. ACM Certificate
- **Domain**: `*.andreas.services` (wildcard)
- **Region**: us-east-1 (required for CloudFront)
- **Purpose**: SSL/TLS for all service subdomains
- **Used by**: All CloudFront distributions

## Why Root-Level?

These resources are **cross-cutting** - they're shared by multiple services:

❌ **Bad**: Each service creates its own certificate
```
storybook/terraform → Creates cert for storybook.andreas.services
humbugg/terraform   → Creates cert for humbugg.andreas.services
```
Problems:
- Hits ACM certificate limits (20 per account)
- Wasteful - each service needs the same wildcard cert
- Destroys can break other services

✅ **Good**: One wildcard cert shared by all services
```
terraform/          → Creates *.andreas.services cert
storybook/terraform → Uses shared cert via data source
humbugg/terraform   → Uses shared cert via data source
```
Benefits:
- Single certificate for all subdomains
- Services can be destroyed without breaking others
- Easier to manage and rotate

## Architecture

```
terraform/                    # ROOT LEVEL (this directory)
├── main.tf                  # Route53 zone + ACM cert
├── outputs.tf               # Exports zone_id, cert_arn
└── backend.tf               # S3 state: root/terraform.tfstate

storybook/terraform/         # SERVICE LEVEL
└── modules/hosting/
    └── main.tf              # References root cert via data source
```

## First-Time Setup

### 1. Initialize and Apply

```bash
cd /Users/andreassavva/Repos/andreas-services/terraform
terraform init
terraform plan
terraform apply
```

This creates:
- Route53 hosted zone for `andreas.services`
- Wildcard ACM certificate for `*.andreas.services`
- DNS validation records

### 2. Update Domain Registrar

After apply, get the name servers:

```bash
terraform output route53_name_servers
```

Update your domain registrar (wherever you bought andreas.services) with these name servers.

### 3. Wait for Certificate Validation

ACM certificate validation can take 5-30 minutes. Check status:

```bash
aws acm describe-certificate \
  --certificate-arn $(terraform output -raw acm_certificate_arn) \
  --region us-east-1 \
  --query 'Certificate.Status'
```

Wait until status is `"ISSUED"`.

## How Services Use This

Services reference the shared infrastructure using Terraform data sources:

```hcl
# In storybook/terraform/modules/hosting/main.tf

# Reference the shared ACM certificate
data "aws_acm_certificate" "wildcard" {
  provider = aws.us_east_1
  domain   = "*.andreas.services"
  statuses = ["ISSUED"]
}

# Reference the shared Route53 zone
data "aws_route53_zone" "main" {
  name = "andreas.services"
}

# Use them in resources
resource "aws_cloudfront_distribution" "app" {
  viewer_certificate {
    acm_certificate_arn = data.aws_acm_certificate.wildcard.arn
    # ...
  }
}

resource "aws_route53_record" "app" {
  zone_id = data.aws_route53_zone.main.zone_id
  # ...
}
```

## Outputs

After `terraform apply`, these outputs are available:

| Output | Description | Used By |
|--------|-------------|---------|
| `route53_zone_id` | Zone ID for creating DNS records | All services |
| `route53_name_servers` | Name servers for domain registrar | Manual setup |
| `acm_certificate_arn` | ARN of wildcard SSL cert | CloudFront distributions |

## State Management

- **Backend**: S3 bucket `andreas-services-terraform-state`
- **State Key**: `root/terraform.tfstate`
- **Separate from services**: Each service has its own state file

```
s3://andreas-services-terraform-state/
├── root/terraform.tfstate              # This infrastructure
├── storybook/dev/terraform.tfstate     # Storybook dev
├── storybook/prod/terraform.tfstate    # Storybook prod
└── humbugg/prod/terraform.tfstate      # Humbugg prod (future)
```

## Destruction Warning

⚠️ **DO NOT DESTROY** these resources unless you're tearing down ALL services.

Destroying this infrastructure will:
- Break all service DNS records
- Invalidate all SSL certificates
- Cause downtime for all applications

Only destroy individual service infrastructure, not root infrastructure.

## Adding a New Service

When adding a new service (e.g., `humbugg`):

1. **No changes needed here** - root infrastructure supports all subdomains
2. In your service terraform, reference the shared resources:
   ```hcl
   data "aws_route53_zone" "main" {
     name = "andreas.services"
   }

   data "aws_acm_certificate" "wildcard" {
     provider = aws.us_east_1
     domain   = "*.andreas.services"
     statuses = ["ISSUED"]
   }
   ```
3. Create your service's DNS record in the shared zone
4. Use the shared ACM certificate in CloudFront

## Troubleshooting

### Certificate not validating
```bash
# Check validation records exist
aws route53 list-resource-record-sets \
  --hosted-zone-id $(terraform output -raw route53_zone_id) \
  --query "ResourceRecordSets[?Type=='CNAME']"
```

### DNS not resolving
```bash
# Check name servers are correct
dig NS andreas.services

# Should match
terraform output route53_name_servers
```

## Support

For questions about root infrastructure, see:
- Individual service docs: `storybook/terraform/README.md`
- AWS Route53 docs: https://docs.aws.amazon.com/route53/
- AWS ACM docs: https://docs.aws.amazon.com/acm/
