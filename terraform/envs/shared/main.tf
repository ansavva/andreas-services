# envs/shared/main.tf
# Shared platform infrastructure: Route53 zone (data source) + ACM wildcard certificate.
#
# The VPC, NAT Gateway, subnets, and DocumentDB cluster have been removed.
# All services now use DynamoDB (IAM-controlled, no VPC required).

locals {
  shared_tags = {
    Project     = "platform"
    Environment = "shared"
    ManagedBy   = "terraform"
    Scope       = "shared"
  }
}

# Route53 hosted zone — managed outside Terraform (registered domain)
data "aws_route53_zone" "main" {
  name         = var.domain_name
  private_zone = false
}

# Wildcard ACM certificate for *.andreas.services (must be in us-east-1 for CloudFront)
resource "aws_acm_certificate" "wildcard" {
  provider          = aws.us_east_1
  domain_name       = "*.${var.domain_name}"
  validation_method = "DNS"

  subject_alternative_names = [var.domain_name]

  lifecycle {
    create_before_destroy = true
  }

  tags = merge(local.shared_tags, {
    Name = "wildcard-${var.domain_name}"
  })
}

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
