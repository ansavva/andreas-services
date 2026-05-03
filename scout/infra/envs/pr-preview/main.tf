locals {
  project     = "scout"
  environment = "pr-preview"

  common_tags = {
    Project     = local.project
    Environment = local.environment
    ManagedBy   = "Terraform"
  }
}

data "aws_route53_zone" "main" {
  name         = "andreas.services"
  private_zone = false
}

module "storage" {
  source = "../../modules/storage"

  bucket_name = "scout-pr-previews"

  tags = local.common_tags
}

module "hosting" {
  source = "../../modules/hosting"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  domain_name         = "scout-pr.andreas.services"
  route53_zone_id     = data.aws_route53_zone.main.zone_id
  s3_website_endpoint = module.storage.website_endpoint

  tags = local.common_tags
}

module "api_domain" {
  source = "../../modules/api_domain"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  domain_name     = "scout-api-pr.andreas.services"
  route53_zone_id = data.aws_route53_zone.main.zone_id

  tags = local.common_tags
}
