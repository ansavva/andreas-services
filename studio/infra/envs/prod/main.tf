locals {
  project     = "studio"
  environment = "prod"

  app_domain = "studio.andreas.services"

  # `studio-api`, not `api.studio`: the shared wildcard certificate covers one
  # label, so a second level would need a certificate of its own. Same shape as
  # website-api.andreas.services.
  api_domain = "studio-api.andreas.services"

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

# NOTE ON THE MEDIA BUCKET.
#
# `var.media_bucket_name` names a bucket the x-harness pipeline owns. It is
# referenced as a string and NOTHING MORE — there is deliberately no
# `aws_s3_bucket` resource and no `aws_s3_bucket` data source for it anywhere in
# this state. A data source would be harmless today but would put the bucket one
# careless refactor away from being managed here, and this state must never be
# able to alter or destroy that data. The only thing studio holds against it is
# the read-only IAM policy in `modules/compute`.

module "auth" {
  source = "../../modules/auth"

  # The pool backs the whole app rather than an admin corner of it, so "app" is
  # the component it serves.
  name = "${local.project}-${local.environment}-app"
  tags = local.common_tags
}

module "compute" {
  source = "../../modules/compute"

  project     = local.project
  environment = local.environment

  media_bucket_name = var.media_bucket_name
  media_root_prefix = var.media_root_prefix
  allowed_origin    = "https://${local.app_domain}"

  tags = local.common_tags
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

  project     = local.project
  environment = local.environment

  lambda_invoke_arn    = module.compute.api_invoke_arn
  lambda_function_name = module.compute.api_function_name

  custom_domain_name = module.api_domain.domain_name
  base_path          = ""
  stage_name         = "prod"

  cognito_user_pool_arn = module.auth.user_pool_arn
  allowed_origin        = "https://${local.app_domain}"

  throttle_rate  = var.api_throttling_rate_limit
  throttle_burst = var.api_throttling_burst_limit

  tags = local.common_tags
}

module "hosting" {
  source = "../../modules/hosting"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  project     = local.project
  environment = local.environment
  domain_name = local.app_domain

  # S3 names are globally unique, so this one carries the region suffix the
  # convention reserves for buckets.
  app_bucket_name = "${local.project}-${local.environment}-app-${data.aws_region.current.name}"

  route53_zone_id = data.aws_route53_zone.main.zone_id
  tags            = local.common_tags
}

# Terraform owns this parameter because Terraform knows the value; the deploy
# workflow reads it back out when building the frontend.
resource "aws_ssm_parameter" "api_domain" {
  name        = "/${local.project}/${local.environment}/api-domain"
  description = "Public base URL of the studio backend API"
  type        = "String"
  value       = module.api_domain.api_base_url

  tags = local.common_tags
}
