# envs/shared/main.tf
# Shared platform infrastructure (Route53, ACM, networking, DocumentDB)

# Route53 Hosted Zone (existing)
data "aws_route53_zone" "main" {
  name         = var.domain_name
  private_zone = false
}

# Wildcard ACM certificate for *.andreas.services
resource "aws_acm_certificate" "wildcard" {
  provider          = aws.us_east_1
  domain_name       = "*.${var.domain_name}"
  validation_method = "DNS"

  subject_alternative_names = [var.domain_name]

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name        = "wildcard-${var.domain_name}"
    ManagedBy   = "terraform"
    Environment = "shared"
  }
}

# DNS validation records
resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.wildcard.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = data.aws_route53_zone.main.zone_id
}

resource "aws_acm_certificate_validation" "wildcard" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.wildcard.arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]
}

locals {
  shared_project     = "platform"
  shared_environment = "shared"

  shared_tags = {
    Project     = local.shared_project
    Environment = local.shared_environment
    ManagedBy   = "terraform"
    Scope       = "shared"
  }
}

# Shared VPC + networking used by apps
module "shared_networking" {
  source = "../../modules/networking"

  project     = local.shared_project
  environment = local.shared_environment
  aws_region  = var.aws_region

  tags = local.shared_tags
}

# Shared DocumentDB cluster
module "shared_database" {
  source = "../../modules/database"

  project     = local.shared_project
  environment = local.shared_environment
  vpc_id      = module.shared_networking.vpc_id
  subnet_ids  = module.shared_networking.private_subnet_ids

  lambda_security_group_ids = []
  master_username           = var.docdb_master_username
  master_password           = var.docdb_master_password

  tags = local.shared_tags
}
