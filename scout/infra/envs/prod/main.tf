locals {
  project     = "scout"
  environment = "production"
  domain_name = "scout.andreas.services"

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
  source = "../../modules/data"

  tags = local.common_tags
}

module "storage" {
  source = "../../modules/storage"

  bucket_name = "${local.project}-web-${local.environment}"

  tags = local.common_tags
}

# Private bucket for source-run artifacts: root bodies, linked-page archives,
# and agent transcripts, organized under runs/<source_id>/<run_id>/.
module "artifacts_storage" {
  source = "../../modules/storage"

  bucket_name = "${local.project}-artifacts-${local.environment}"

  tags = local.common_tags
}

# Private bucket for event images (admin-uploaded + auto-extracted), kept
# separate from source-body storage per the data model.
module "images_storage" {
  source = "../../modules/storage"

  bucket_name = "${local.project}-images-${local.environment}"

  tags = local.common_tags
}

import {
  to = module.compute.aws_ecr_repository.events_api[0]
  id = "scout-events-api"
}

import {
  to = module.compute.aws_ecr_repository.renderer[0]
  id = "scout-renderer"
}

import {
  to = module.hosting.aws_cloudfront_function.spa_fallback
  id = "scout-spa-fallback"
}

import {
  to = module.compute.aws_cloudwatch_log_group.events_api
  id = "/aws/lambda/scout-events-api"
}

module "compute" {
  source = "../../modules/compute"

  create_ecr         = true
  create_eventbridge = true

  core_table_name     = module.data.core_table_name
  settings_table_name = module.data.settings_table_name

  artifacts_bucket = module.artifacts_storage.bucket_id
  images_bucket    = module.images_storage.bucket_id

  processor_env_vars = {
    ANTHROPIC_API_KEY = var.anthropic_api_key
  }

  tags = local.common_tags
}

module "api_domain" {
  source = "../../modules/api_domain"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  domain_name     = "scout-api.andreas.services"
  route53_zone_id = data.aws_route53_zone.main.zone_id

  tags = local.common_tags
}

module "auth" {
  source = "../../modules/auth"

  name = "scout"
  callback_urls = [
    "https://${local.domain_name}/app",
    "http://localhost:5173/app",
  ]
  logout_urls = [
    "https://${local.domain_name}/app",
    "http://localhost:5173/app",
  ]

  tags = local.common_tags
}

module "api_gateway" {
  source = "../../modules/api_gateway"

  lambda_invoke_arn         = module.compute.events_api_invoke_arn
  lambda_function_name      = module.compute.events_api_function_name
  custom_domain_name        = module.api_domain.domain_name
  base_path                 = ""
  stage_name                = "prod"
  throttle_rate             = 10
  throttle_burst            = 50
  cognito_user_pool_arn     = module.auth.user_pool_arn
  enable_cognito_authorizer = true

  tags = local.common_tags
}

module "hosting" {
  source = "../../modules/hosting"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  domain_name                    = local.domain_name
  route53_zone_id                = data.aws_route53_zone.main.zone_id
  s3_bucket_id                   = module.storage.bucket_id
  s3_bucket_arn                  = module.storage.bucket_arn
  s3_bucket_regional_domain_name = module.storage.bucket_regional_domain_name

  tags = local.common_tags
}
