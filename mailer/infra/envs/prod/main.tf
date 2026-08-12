locals {
  project     = "mailer"
  environment = "prod"
  domain_name = "mailer-api.andreas.services"

  common_tags = {
    Project     = local.project
    Environment = local.environment
    Owner       = "ansavva"
    ManagedBy   = "terraform"
  }
}

data "aws_route53_zone" "main" {
  name         = "andreas.services"
  private_zone = false
}

module "platform" {
  source = "../../modules/platform"

  project                = local.project
  environment            = local.environment
  domain_name            = local.domain_name
  route53_zone_id        = data.aws_route53_zone.main.zone_id
  humbugg_role_name      = var.humbugg_role_name
  humbugg_sender_address = "no-reply@humbugg.com"
  tags                   = local.common_tags
}
