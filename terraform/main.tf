# Root-level infrastructure for andreas.services
# This file manages cross-cutting resources shared by all services

# Route53 Hosted Zone
# Reference the existing hosted zone created by Route53 Registrar when you bought the domain
# DO NOT create a new hosted zone - use the one AWS created
data "aws_route53_zone" "main" {
  name         = var.domain_name
  private_zone = false
}

# Wildcard ACM Certificate for *.andreas.services
# Must be in us-east-1 for use with CloudFront
resource "aws_acm_certificate" "wildcard" {
  provider          = aws.us_east_1
  domain_name       = "*.${var.domain_name}"
  validation_method = "DNS"

  # Also include the root domain
  subject_alternative_names = [var.domain_name]

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name        = "wildcard-andreas-services"
    ManagedBy   = "terraform"
    Environment = "shared"
  }
}

# Route53 records for certificate validation
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

# ACM Certificate Validation
resource "aws_acm_certificate_validation" "wildcard" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.wildcard.arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]
}
