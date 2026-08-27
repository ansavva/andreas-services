locals {
  project     = "scout"
  environment = "prod"
  region      = "us-east-1"
  domain_name = "scout.andreas.services"

  name_prefix = "${local.project}-${local.environment}"

  common_tags = {
    Project     = local.project
    Environment = local.environment
    Owner       = "ansavva"
    ManagedBy   = "Terraform"
  }
}

data "aws_route53_zone" "main" {
  name         = "andreas.services"
  private_zone = false
}

# Cognito custom domains, like CloudFront, take a us-east-1 certificate.
data "aws_acm_certificate" "wildcard" {
  provider    = aws.us_east_1
  domain      = "*.andreas.services"
  statuses    = ["ISSUED"]
  most_recent = true
}

module "data" {
  source = "../../modules/data"

  project     = local.project
  environment = local.environment

  tags = local.common_tags
}

module "storage" {
  source = "../../modules/storage"

  bucket_name = "${local.name_prefix}-web-${local.region}"

  # Set ahead of the rename: Terraform applies the destroy half of a
  # replacement against prior state, so this flag must already be recorded in
  # state before the bucket name changes (see CLAUDE.md).
  force_destroy = true

  tags = local.common_tags
}

# Private bucket for source-run artifacts: root bodies, linked-page archives,
# and agent transcripts, organized under runs/<source_id>/<run_id>/.
module "artifacts_storage" {
  source = "../../modules/storage"

  bucket_name   = "${local.name_prefix}-artifacts-${local.region}"
  force_destroy = true

  tags = local.common_tags
}

# Private bucket for event images (admin-uploaded + auto-extracted), kept
# separate from source-body storage per the data model.
module "images_storage" {
  source = "../../modules/storage"

  bucket_name   = "${local.name_prefix}-images-${local.region}"
  force_destroy = true

  tags = local.common_tags
}

module "compute" {
  source = "../../modules/compute"

  project     = local.project
  environment = local.environment

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

  name = local.name_prefix
  # Exact-match, character for character — no wildcard host, path or port. The
  # code flow redirects only to /app/auth/callback, so only that is registered
  # here; the bare origins belong in logout_urls, below.
  callback_urls = [
    "https://${local.domain_name}/app/auth/callback",
    "http://localhost:5173/app/auth/callback",
  ]
  logout_urls = [
    "https://${local.domain_name}/app",
    "http://localhost:5173/app",
  ]

  auth_domain          = "scout-auth.andreas.services"
  auth_certificate_arn = data.aws_acm_certificate.wildcard.arn
  route53_zone_id      = data.aws_route53_zone.main.zone_id

  tags = local.common_tags
}

module "api_gateway" {
  source = "../../modules/api_gateway"

  project     = local.project
  environment = local.environment

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

  project     = local.project
  environment = local.environment

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
