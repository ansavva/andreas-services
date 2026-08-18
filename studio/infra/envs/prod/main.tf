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

# THE MEDIA BUCKET — and the archive it is being renamed out of.
#
# Studio owns this bucket. It used to be the other way round: the bucket was
# provisioned from a separate `xharness` repo, and this file carried a long note
# forbidding any resource or data source for it, so that studio's state could
# never touch data it did not own. That note is gone because the premise is —
# the generation pipeline that fills the bucket now lives in `.claude/skills/`
# alongside the app that reads it, and the bucket was imported into this state
# in August 2026.
#
# It is now being renamed to `studio-prod-media-us-east-1`, which the original
# name never matched. An S3 bucket cannot actually be renamed: changing the
# `bucket` argument is a destroy-and-recreate, and a destroy-and-recreate of
# THIS bucket is unacceptable. So the "rename" is a second bucket plus a copy,
# in three separate applies, and this file is at step 1 of 3:
#
#   1. DONE — renamed the module address. `module.media` became
#      `module.media_archive` via a `moved` block: a state edit, no AWS resource
#      created, changed or destroyed. Terraform forbids declaring `module.media`
#      again while such a block names it as a source, which is why creating the
#      new bucket could not be folded into it.
#   2. THIS APPLY — create `module.media`, the new correctly-named bucket. It is
#      EMPTY and nothing reads it. The app keeps reading the archive.
#   3. Copy the current objects across, verify, then flip `local.active_media`.
#
# The archive is retained permanently at the end of it, and that is the point
# rather than an oversight. It holds 1,613 noncurrent object versions and 718
# keys that exist only behind a delete marker — deleted, still recoverable. A
# copy of current objects carries none of that, so deleting the archive would
# destroy exactly the recovery history the versioning on these buckets exists to
# provide. Both buckets carry `prevent_destroy`, which means `terraform destroy`
# on this whole environment fails by design (see `modules/media/main.tf`).

module "media" {
  source = "../../modules/media"

  bucket_name = var.media_bucket_name
  key_prefix  = var.media_root_prefix

  tags = local.common_tags
}

module "media_archive" {
  source = "../../modules/media"

  bucket_name = var.media_archive_bucket_name
  key_prefix  = var.media_root_prefix

  tags = local.common_tags
}

# THE CUTOVER SEAM.
#
# Everything downstream — the API's IAM policy, the Lambda's env var, the SSM
# parameter the skills and `dev-setup.sh` read — follows this local rather than
# a module reference, so that moving the pipeline from one bucket to the other
# is a one-line change in its own commit, and a one-line revert.
#
# It still points at the archive. `module.media` above now exists, but it is
# empty — pointing the app at it before the copy would take studio down for the
# length of the transfer, and serve 404s for every asset in the meantime. It
# moves in step 3, after the copy is verified.
locals {
  active_media = module.media_archive
}

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

  # From the module, not from the variable directly: this is what orders the
  # IAM policy after the bucket exists.
  media_bucket_name = local.active_media.bucket_name
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
