# Custom domain for the backend HTTP API (api.humbugg.com). This is additive: the API keeps
# answering through the CloudFront /api/* behavior on the application distribution, and now
# also answers directly on its own hostname.
#
# The certificate comes from modules/certificates rather than a data source, so the domain
# cannot be created before ACM has issued it. A REGIONAL endpoint needs its certificate in
# the API's own region — us-east-1 here, which is also where CloudFront requires it, so one
# certificate serves both.
resource "aws_apigatewayv2_domain_name" "api" {
  domain_name = var.domain_name

  domain_name_configuration {
    certificate_arn = var.certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }

  tags = var.tags
}

# Maps the domain root onto the existing backend stage — no api_mapping_key, so
# https://api.humbugg.com/api/... reaches the same routes as the stage invoke URL.
resource "aws_apigatewayv2_api_mapping" "api" {
  api_id      = var.api_id
  domain_name = aws_apigatewayv2_domain_name.api.id
  stage       = var.stage_name
}

resource "aws_route53_record" "api" {
  for_each = toset(["A", "AAAA"])

  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = each.value

  alias {
    name                   = aws_apigatewayv2_domain_name.api.domain_name_configuration[0].target_domain_name
    zone_id                = aws_apigatewayv2_domain_name.api.domain_name_configuration[0].hosted_zone_id
    evaluate_target_health = false
  }
}
