locals {
  project     = "website"
  environment = "prod"

  www_domain  = "www.andreas.services"
  apex_domain = "andreas.services"
  api_domain  = "website-api.andreas.services"

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

data "aws_region" "current" {}

module "data" {
  source      = "../../modules/data"
  project     = local.project
  environment = local.environment
  tags        = local.common_tags
}

# The pool backs the admin dashboard only — no public sign-up — so "admin" is
# the component it serves.
module "auth" {
  source = "../../modules/auth"
  name   = "${local.project}-${local.environment}-admin"
  tags   = local.common_tags
}

module "compute" {
  source            = "../../modules/compute"
  project           = local.project
  environment       = local.environment
  create_ecr        = true
  intake_table_arn  = module.data.intake_table_arn
  intake_table_name = module.data.intake_table_name
  tags              = local.common_tags
}

module "api_domain" {
  source = "../../modules/api_domain"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  domain_name     = local.api_domain
  route53_zone_id = data.aws_route53_zone.main.zone_id
  tags            = local.common_tags
}

module "api_gateway" {
  source = "../../modules/api_gateway"

  project                   = local.project
  environment               = local.environment
  lambda_invoke_arn         = module.compute.api_invoke_arn
  lambda_function_name      = module.compute.api_function_name
  custom_domain_name        = module.api_domain.domain_name
  base_path                 = ""
  stage_name                = "prod"
  cognito_user_pool_arn     = module.auth.user_pool_arn
  enable_cognito_authorizer = true
  allowed_origin            = "https://${local.www_domain}"
  tags                      = local.common_tags
}

module "hosting" {
  source = "../../modules/hosting"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  project     = local.project
  environment = local.environment
  www_domain  = local.www_domain
  apex_domain = local.apex_domain

  # S3 names are globally unique, so this one carries the region suffix the
  # convention reserves for buckets.
  assets_bucket_name = "${local.project}-${local.environment}-assets-${data.aws_region.current.name}"

  www_api_domain  = module.compute.www_api_domain
  route53_zone_id = data.aws_route53_zone.main.zone_id
  tags            = local.common_tags
}
