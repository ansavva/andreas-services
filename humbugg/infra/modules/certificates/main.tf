# The one TLS certificate every Humbugg edge uses. It lives outside `hosting` because two
# unrelated consumers need the same ARN: the CloudFront distribution and the regional API
# Gateway custom domain for api.humbugg.com. us-east-1 does double duty here — it is the
# region CloudFront requires for its viewer certificate, and it is also this deployment's
# own region, so a REGIONAL API Gateway domain can use the very same certificate.
terraform {
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      configuration_aliases = [aws.us_east_1]
    }
  }
}

resource "aws_acm_certificate" "main" {
  provider                  = aws.us_east_1
  domain_name               = var.domain_name
  subject_alternative_names = var.subject_alternative_names
  validation_method         = "DNS"

  # Changing the SAN list replaces the certificate rather than updating it. Creating the
  # replacement before destroying the old one keeps whatever is already serving it online
  # through the swap.
  lifecycle {
    create_before_destroy = true
  }

  tags = var.tags
}

# Every name on the certificate lives under humbugg.com, so all validation records go to
# that one zone. ACM emits one validation option per name.
resource "aws_route53_record" "certificate_validation" {
  for_each = {
    for option in aws_acm_certificate.main.domain_validation_options : option.domain_name => {
      name   = option.resource_record_name
      record = option.resource_record_value
      type   = option.resource_record_type
    }
  }

  allow_overwrite = true
  zone_id         = var.route53_zone_id
  name            = each.value.name
  type            = each.value.type
  ttl             = 300
  records         = [each.value.record]
}

resource "aws_acm_certificate_validation" "main" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.main.arn
  validation_record_fqdns = [for record in aws_route53_record.certificate_validation : record.fqdn]
}
