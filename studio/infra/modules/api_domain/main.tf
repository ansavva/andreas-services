terraform {
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      configuration_aliases = [aws.us_east_1]
    }
  }
}

# Custom domain for the backend API (studio-api.andreas.services), fronted by
# the shared *.andreas.services wildcard certificate.
#
# The name is `studio-api` rather than `api.studio` on purpose: a wildcard
# certificate covers exactly one label, so `api.studio.andreas.services` would
# NOT be covered and would need a certificate of its own. `website-api` sets the
# same precedent.
data "aws_acm_certificate" "wildcard" {
  provider    = aws.us_east_1
  domain      = "*.andreas.services"
  statuses    = ["ISSUED"]
  most_recent = true
}

resource "aws_api_gateway_domain_name" "main" {
  domain_name              = var.domain_name
  regional_certificate_arn = data.aws_acm_certificate.wildcard.arn

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = var.tags
}

resource "aws_route53_record" "api" {
  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_api_gateway_domain_name.main.regional_domain_name
    zone_id                = aws_api_gateway_domain_name.main.regional_zone_id
    evaluate_target_health = false
  }
}
