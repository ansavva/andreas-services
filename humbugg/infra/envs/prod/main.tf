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
  domain_name = local.domain_name

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
  avatars_bucket_arn       = module.storage.app_bucket_arn
  mailer_status_queue_arn  = data.aws_ssm_parameter.mailer_status_queue_arn.value
  cognito_user_pool_id     = module.auth.user_pool_id
  cognito_client_id        = module.auth.user_pool_client_id

  api_throttling_rate_limit  = var.api_throttling_rate_limit
  api_throttling_burst_limit = var.api_throttling_burst_limit

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

  avatars_bucket_id                   = module.storage.app_bucket_id
  avatars_bucket_arn                  = module.storage.app_bucket_arn
  avatars_bucket_regional_domain_name = module.storage.app_bucket_regional_domain_name

  api_endpoint        = module.compute.api_endpoint
  frontend_api_domain = module.compute.frontend_api_domain

  tags = local.common_tags
}

module "email" {
  source = "../../modules/email"

  aws_region      = var.aws_region
  domain_name     = local.domain_name
  route53_zone_id = data.aws_route53_zone.humbugg.zone_id

  # DKIM public key generated in Google Admin (Apps → Gmail → Authenticate
  # email). Empty until generated; the record is created once set.
  google_dkim_txt_value = ""

  # The manually created google-site-verification string lives at the apex;
  # the single managed apex TXT record set must carry it alongside SPF.
  # Public value — safe to commit. Never remove it: Google re-checks it.
  apex_txt_additional_records = ["google-site-verification=Ty65XWNQL5fqun83W2_nuKQGbXwmS5IRTHDpU9up1gQ"]
}

# The apex MX moved from the retired SES-inbound stack to the email module,
# where its value flipped to Google Workspace. The moved block turns what
# would be a same-name delete+create race into an in-place update.
moved {
  from = module.support_forwarding.aws_route53_record.inbound_mx
  to   = module.email.aws_route53_record.apex_mx
}

module "billing" {
  source = "../../modules/billing"

  project     = local.project
  environment = local.environment

  stripe_publishable_key = var.stripe_publishable_key
  stripe_secret_key      = var.stripe_secret_key
  stripe_webhook_secret  = var.stripe_webhook_secret

  tags = local.common_tags
}

