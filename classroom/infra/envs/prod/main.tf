locals {
  project     = "classroom"
  environment = "prod"
  region      = "us-east-1"
  domain_name = "classroom.andreas.services"

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

  # Build output only, so it is regenerable. Set at creation, not retrofitted:
  # Terraform applies the destroy half of a replacement against prior state.
  force_destroy = true

  tags = local.common_tags
}

module "compute" {
  source = "../../modules/compute"

  project     = local.project
  environment = local.environment

  create_ecr = true

  pages_table_name = module.data.pages_table_name
  pages_table_arn  = module.data.pages_table_arn

  public_site_url = "https://${local.domain_name}"

  tags = local.common_tags
}

module "api_domain" {
  source = "../../modules/api_domain"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  domain_name     = "classroom-api.andreas.services"
  route53_zone_id = data.aws_route53_zone.main.zone_id

  tags = local.common_tags
}

module "auth" {
  source = "../../modules/auth"

  name = local.name_prefix

  # Exact-match, character for character — no wildcard host, path or port. The
  # SPA is mounted at the root, so the callback is /auth/callback and must
  # agree with `CALLBACK_PATH` in frontend/src/auth/oauth.ts.
  callback_urls = [
    "https://${local.domain_name}/auth/callback",
    "http://localhost:5174/auth/callback",
  ]
  logout_urls = [
    "https://${local.domain_name}/",
    "http://localhost:5174/",
  ]

  auth_domain          = "classroom-auth.andreas.services"
  auth_certificate_arn = data.aws_acm_certificate.wildcard.arn
  route53_zone_id      = data.aws_route53_zone.main.zone_id

  tags = local.common_tags
}

module "api_gateway" {
  source = "../../modules/api_gateway"

  project     = local.project
  environment = local.environment

  lambda_invoke_arn         = module.compute.api_invoke_arn
  lambda_function_name      = module.compute.api_function_name
  custom_domain_name        = module.api_domain.domain_name
  base_path                 = ""
  stage_name                = "prod"
  throttle_rate             = 20
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

# --- values the deploy workflow reads back --------------------------------

resource "aws_ssm_parameter" "frontend_bucket" {
  name  = "/${local.project}/${local.environment}/frontend-bucket"
  type  = "String"
  value = module.storage.bucket_id
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "distribution_id" {
  name  = "/${local.project}/${local.environment}/distribution-id"
  type  = "String"
  value = module.hosting.distribution_id
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "api_url" {
  name  = "/${local.project}/${local.environment}/api-url"
  type  = "String"
  value = module.api_gateway.invoke_url
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "cognito_client_id" {
  name  = "/${local.project}/${local.environment}/cognito-client-id"
  type  = "String"
  value = module.auth.user_pool_client_id
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "cognito_domain" {
  name  = "/${local.project}/${local.environment}/cognito-domain"
  type  = "String"
  value = module.auth.auth_domain
  tags  = local.common_tags
}
