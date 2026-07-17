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

data "aws_ssm_parameter" "mailer_status_queue_arn" {
  name = "/mailer/prod/humbugg/status-queue-arn"
}

data "aws_ssm_parameter" "mailer_auth_configuration_set" {
  name = "/mailer/prod/humbugg/auth-configuration-set"
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

  email_sending_account   = "DEVELOPER"
  email_from_address      = module.email.from_address
  email_source_arn        = module.email.identity_arn
  email_configuration_set = data.aws_ssm_parameter.mailer_auth_configuration_set.value

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
  mailer_status_queue_arn  = data.aws_ssm_parameter.mailer_status_queue_arn.value
  cognito_user_pool_id     = module.auth.user_pool_id
  cognito_client_id        = module.auth.user_pool_client_id

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

module "support_forwarding" {
  source = "../../modules/support_forwarding"

  project     = local.project
  environment = local.environment
  aws_region  = var.aws_region

  domain_name       = local.domain_name
  route53_zone_id   = data.aws_route53_zone.humbugg.zone_id
  support_recipient = "support@${local.domain_name}"

  from_address     = module.email.from_address
  ses_identity_arn = module.email.identity_arn

  # Human-provided secret; injected via TF_VAR_support_forward_to in CI. Empty
  # here so nothing sensitive is committed.
  support_forward_to = var.support_forward_to

  lambda_source_dir = "${path.module}/../../../support-forwarding/src"

  tags = local.common_tags
}
