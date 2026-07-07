locals {
  project     = "website"
  environment = "production"

  www_domain  = "www.andreas.services"
  apex_domain = "andreas.services"
  api_domain  = "website-api.andreas.services"

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

module "data" {
  source       = "../../modules/data"
  table_suffix = ""
  tags         = local.common_tags
}

module "auth" {
  source = "../../modules/auth"
  name   = "website"
  tags   = local.common_tags
}

import {
  to = module.compute.aws_ecr_repository.api[0]
  id = "website-api"
}

import {
  to = module.compute.aws_ecr_repository.frontend[0]
  id = "website-frontend"
}

module "compute" {
  source           = "../../modules/compute"
  table_suffix     = ""
  create_ecr       = true
  intake_table_arn = module.data.intake_table_arn
  tags             = local.common_tags
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

  www_domain             = local.www_domain
  apex_domain            = local.apex_domain
  assets_bucket_name     = "andreas-services-website-assets-${local.environment}"
  frontend_function_url  = module.compute.frontend_function_url
  frontend_function_name = module.compute.frontend_function_name
  route53_zone_id        = data.aws_route53_zone.main.zone_id
  tags                   = local.common_tags
}
