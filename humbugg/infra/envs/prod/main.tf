locals {
  project          = "humbugg"
  environment      = "prod"
  domain_name      = "humbugg.com"
  api_domain_name  = "api.${local.domain_name}"
  auth_domain_name = "auth.${local.domain_name}"

  # What the backend derives invite URLs and avatar URLs from, and what Cognito
  # redirects to — so it is the product app, not the marketing site. The
  # marketing origin has no Terraform consumer; it is a build-time value the
  # deploy workflow passes to Vite.
  app_base_url = "https://app.${local.domain_name}"

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

data "aws_ssm_parameter" "mailer_status_queue_arn" {
  name = "/mailer/prod/humbugg/status-queue-arn"
}

data "aws_ssm_parameter" "mailer_auth_configuration_set" {
  name = "/mailer/prod/humbugg/auth-configuration-set"
}

module "auth" {
  source = "../../modules/auth"

  project     = local.project
  environment = local.environment

  # Two literals per list because the same codebase produces two redirects: the
  # web export served from app.humbugg.com, and the custom scheme a store build
  # returns to. Cognito matches exactly, so a bare origin is not a callback and
  # a missing entry is a hard `redirect_mismatch`.
  callback_urls = ["${local.app_base_url}/auth/callback", "humbugg://auth/callback"]
  logout_urls   = ["${local.app_base_url}/login", "humbugg://auth/logout"]

  auth_domain          = local.auth_domain_name
  auth_certificate_arn = module.certificates.certificate_arn
  route53_zone_id      = data.aws_route53_zone.humbugg.zone_id

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
  aws_region  = var.aws_region
  domain_name = local.domain_name

  tags = local.common_tags
}

module "compute" {
  source = "../../modules/compute"

  project     = local.project
  environment = local.environment

  dynamodb_table_arns      = module.storage.dynamodb_table_arns
  email_messages_table_arn = module.storage.email_messages_table_arn
  # app_files, not app: the SPA bundle and user uploads live in separate buckets, and
  # the Lambda writes avatars to the files one (HUMBUGG_APP_BUCKET). Granting it against
  # the hosting bucket made every avatar upload a 500 — AccessDenied on PutObject.
  avatars_bucket_arn      = module.storage.app_files_bucket_arn
  mailer_status_queue_arn = data.aws_ssm_parameter.mailer_status_queue_arn.value
  cognito_user_pool_id    = module.auth.user_pool_id
  cognito_user_pool_arn   = module.auth.user_pool_arn
  cognito_client_id       = module.auth.user_pool_client_id

  api_throttling_rate_limit  = var.api_throttling_rate_limit
  api_throttling_burst_limit = var.api_throttling_burst_limit

  tags = local.common_tags
}

module "certificates" {
  source = "../../modules/certificates"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  domain_name = local.domain_name

  # Every name Humbugg serves. Adding one later replaces the certificate, so the full
  # set is declared up front rather than grown surface by surface.
  #
  # `auth.` was added after the fact anyway, when sign-in moved to Managed Login
  # (#365) — a replacement, not an update. `create_before_destroy` in
  # modules/certificates makes that survivable: the new certificate is issued and
  # every consumer repointed before the old one goes, so www, app and api keep
  # serving through the swap.
  subject_alternative_names = [
    "www.${local.domain_name}",
    "app.${local.domain_name}",
    local.api_domain_name,
    local.auth_domain_name,
  ]

  route53_zone_id = data.aws_route53_zone.humbugg.zone_id

  tags = local.common_tags
}

# api.humbugg.com answers alongside the existing humbugg.com/api/* CloudFront path.
# Nothing is cut over here: no caller is repointed and the CloudFront behavior is untouched.
module "api_domain" {
  source = "../../modules/api_domain"

  domain_name     = local.api_domain_name
  certificate_arn = module.certificates.certificate_arn

  api_id     = module.compute.api_id
  stage_name = module.compute.api_stage_name

  route53_zone_id = data.aws_route53_zone.humbugg.zone_id

  tags = local.common_tags
}

# Terraform owns this parameter because Terraform knows the value; the deploy workflow's
# put-parameter step exists for outputs the app jobs consume, and can read this one.
resource "aws_ssm_parameter" "api_domain" {
  name        = "/humbugg/prod/api-domain"
  description = "Public base URL of the backend API on its own domain"
  type        = "String"
  value       = module.api_domain.api_base_url

  tags = local.common_tags
}

module "hosting_marketing" {
  source = "../../modules/hosting_marketing"

  environment = local.environment
  project     = local.project
  domain_name = local.domain_name

  certificate_arn = module.certificates.certificate_arn

  route53_zone_id = data.aws_route53_zone.humbugg.zone_id

  marketing_bucket_id                   = module.storage.marketing_bucket_id
  marketing_bucket_arn                  = module.storage.marketing_bucket_arn
  marketing_bucket_regional_domain_name = module.storage.marketing_bucket_regional_domain_name

  marketing_api_domain = module.compute.marketing_api_domain

  tags = local.common_tags
}

module "hosting_app" {
  source = "../../modules/hosting_app"

  environment = local.environment
  project     = local.project
  domain_name = local.domain_name

  certificate_arn = module.certificates.certificate_arn
  route53_zone_id = data.aws_route53_zone.humbugg.zone_id

  app_bucket_id                   = module.storage.app_bucket_id
  app_bucket_arn                  = module.storage.app_bucket_arn
  app_bucket_regional_domain_name = module.storage.app_bucket_regional_domain_name

  app_files_bucket_id                   = module.storage.app_files_bucket_id
  app_files_bucket_arn                  = module.storage.app_files_bucket_arn
  app_files_bucket_regional_domain_name = module.storage.app_files_bucket_regional_domain_name

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

module "billing" {
  source = "../../modules/billing"

  project     = local.project
  environment = local.environment

  stripe_publishable_key = var.stripe_publishable_key
  stripe_secret_key      = var.stripe_secret_key
  stripe_webhook_secret  = var.stripe_webhook_secret

  tags = local.common_tags
}

module "alerting" {
  source = "../../modules/alerting"

  project     = local.project
  environment = local.environment

  alert_email = var.alert_email

  # `email-status` keeps its original threshold of 1: every error is a delivery status
  # that never reached the ledger. The rest tolerate 2 errors in five minutes so a lone
  # cold-start failure does not mail anyone. Throttles are alarmed for the request-path
  # Lambda only — the consumers are asynchronous and retry.
  lambda_functions = {
    api = {
      function_name   = module.compute.lambda_function_name
      error_threshold = 3
      throttle_alarm  = true
    }
    reminders = {
      function_name   = module.compute.reminders_lambda_function_name
      error_threshold = 3
    }
    marketing = {
      function_name   = module.compute.marketing_lambda_function_name
      error_threshold = 3
    }
    "email-status" = {
      function_name   = module.compute.email_status_lambda_function_name
      error_threshold = 1
    }
  }

  api_ids = {
    api       = module.compute.api_id
    marketing = module.compute.marketing_api_id
  }

  dynamodb_table_names = module.storage.dynamodb_table_names

  tags = local.common_tags
}

# The alarm predates the module. `moved` keeps the same AWS alarm — it is relocated in
# state, not replaced, so nothing is destroyed and no alarm history is lost.
moved {
  from = module.compute.aws_cloudwatch_metric_alarm.email_status_errors
  to   = module.alerting.aws_cloudwatch_metric_alarm.lambda_errors["email-status"]
}

# Published for future consumers — another stack that wants to notify the same place
# reads this rather than duplicating a topic.
resource "aws_ssm_parameter" "alerts_topic_arn" {
  name        = "/humbugg/prod/alerts-topic-arn"
  description = "SNS topic every Humbugg production alarm publishes to"
  type        = "String"
  value       = module.alerting.topic_arn

  tags = local.common_tags
}

