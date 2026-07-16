locals {
  project            = "humbugg"
  environment        = "production"
  domain_name        = "humbugg.com"
  legacy_domain_name = "humbugg.andreas.services"
  app_base_url       = "https://${local.domain_name}"

  common_tags = {
    Project     = local.project
    Environment = local.environment
    ManagedBy   = "Terraform"
  }

}

data "aws_route53_zone" "humbugg" {
  name         = "humbugg.com"
  private_zone = false
}

data "aws_route53_zone" "main" {
  name         = "andreas.services"
  private_zone = false
}

moved {
  from = aws_dynamodb_table.profiles
  to   = module.storage.aws_dynamodb_table.profiles
}

moved {
  from = aws_dynamodb_table.groups
  to   = module.storage.aws_dynamodb_table.groups
}

moved {
  from = aws_dynamodb_table.groupmembers
  to   = module.storage.aws_dynamodb_table.groupmembers
}

module "auth" {
  source = "../../modules/auth"

  project       = local.project
  environment   = local.environment
  callback_urls = [local.app_base_url]
  logout_urls   = [local.app_base_url]

  tags = local.common_tags
}

module "storage" {
  source = "../../modules/storage"

  project     = local.project
  environment = local.environment

  tags = local.common_tags
}

import {
  to = module.compute.aws_ecr_repository.backend
  id = "humbugg-backend-production"
}

import {
  to = module.compute.aws_ecr_repository.frontend
  id = "humbugg-frontend-production"
}

module "compute" {
  source = "../../modules/compute"

  project     = local.project
  environment = local.environment

  dynamodb_table_arns      = module.storage.dynamodb_table_arns
  email_messages_table_arn = module.storage.email_messages_table_arn
  cognito_user_pool_id     = module.auth.user_pool_id
  cognito_client_id        = module.auth.user_pool_client_id
  ses_identity_arn         = module.email.identity_arn

  tags = local.common_tags
}

module "hosting" {
  source = "../../modules/hosting"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  project            = local.project
  domain_name        = local.domain_name
  legacy_domain_name = local.legacy_domain_name

  route53_zone_id        = data.aws_route53_zone.humbugg.zone_id
  legacy_route53_zone_id = data.aws_route53_zone.main.zone_id

  frontend_bucket_id                   = module.storage.bucket_id
  frontend_bucket_arn                  = module.storage.bucket_arn
  frontend_bucket_regional_domain_name = module.storage.bucket_regional_domain_name

  api_endpoint        = module.compute.api_endpoint
  frontend_api_domain = module.compute.frontend_api_domain

  tags = local.common_tags
}

module "email" {
  source = "../../modules/email"

  aws_region      = var.aws_region
  domain_name     = local.domain_name
  route53_zone_id = data.aws_route53_zone.humbugg.zone_id
}
