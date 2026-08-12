locals {
  project            = "humbugg"
  environment        = "prod"
  domain_name        = "humbugg.com"
  legacy_domain_name = "humbugg.andreas.services"
  api_domain_name    = "api.${local.domain_name}"

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
  avatars_bucket_arn       = module.storage.app_bucket_arn
  mailer_status_queue_arn  = data.aws_ssm_parameter.mailer_status_queue_arn.value
  cognito_user_pool_id     = module.auth.user_pool_id
  cognito_client_id        = module.auth.user_pool_client_id

  api_throttling_rate_limit  = var.api_throttling_rate_limit
  api_throttling_burst_limit = var.api_throttling_burst_limit

  tags = local.common_tags
}

# The certificate moved out of `hosting` so the API Gateway custom domain can share it.
# The moved blocks below keep the existing certificate, its validation records, and the
# validation resource attached to their state addresses — a plan that shows any of them
# being destroyed and recreated means one of those addresses is wrong.
moved {
  from = module.hosting.aws_acm_certificate.app
  to   = module.certificates.aws_acm_certificate.main
}

moved {
  from = module.hosting.aws_route53_record.certificate_validation
  to   = module.certificates.aws_route53_record.certificate_validation
}

moved {
  from = module.hosting.aws_acm_certificate_validation.app
  to   = module.certificates.aws_acm_certificate_validation.main
}

module "certificates" {
  source = "../../modules/certificates"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  domain_name        = local.domain_name
  legacy_domain_name = local.legacy_domain_name

  # www and the legacy hostname are served today; app. and api. are added ahead of the
  # surfaces that will use them, because adding a SAN later replaces the certificate.
  subject_alternative_names = [
    "www.${local.domain_name}",
    "app.${local.domain_name}",
    local.api_domain_name,
    local.legacy_domain_name,
  ]

  route53_zone_id        = data.aws_route53_zone.humbugg.zone_id
  legacy_route53_zone_id = data.aws_route53_zone.main.zone_id

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

# modules/hosting became modules/hosting_marketing. The distribution and its
# Route53 aliases carry no name attribute, so this is a state move and not a
# replacement — read the plan and confirm it says "moved", not "destroy".
moved {
  from = module.hosting.aws_cloudfront_distribution.app
  to   = module.hosting_marketing.aws_cloudfront_distribution.app
}

moved {
  from = module.hosting.aws_route53_record.app
  to   = module.hosting_marketing.aws_route53_record.app
}

moved {
  from = module.hosting.aws_route53_record.legacy_ipv6
  to   = module.hosting_marketing.aws_route53_record.legacy_ipv6
}

moved {
  from = module.hosting.aws_route53_record.canonical
  to   = module.hosting_marketing.aws_route53_record.canonical
}

moved {
  from = module.hosting.aws_route53_record.www
  to   = module.hosting_marketing.aws_route53_record.www
}

module "hosting_marketing" {
  source = "../../modules/hosting_marketing"

  environment        = local.environment
  project            = local.project
  domain_name        = local.domain_name
  legacy_domain_name = local.legacy_domain_name

  certificate_arn = module.certificates.certificate_arn

  route53_zone_id        = data.aws_route53_zone.humbugg.zone_id
  legacy_route53_zone_id = data.aws_route53_zone.main.zone_id

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

