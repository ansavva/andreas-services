locals {
  project     = "classroom"
  environment = "prod"
  region      = "us-east-1"
  # TWO HOSTS, AND THE SPLIT IS THE SECURITY MODEL.
  #
  # Lessons are interactive — the teacher's uploads run their own JavaScript —
  # so nothing sanitizes them and no CSP blocks their scripts. What keeps that
  # safe is that they are served from a DIFFERENT ORIGIN to the app she signs
  # in to: her session tokens live in `localStorage` on the admin host, and
  # `localStorage` is origin-scoped, so lesson code cannot reach them.
  #
  # The short host is the STUDENTS' one, deliberately: it is the link that goes
  # on a whiteboard. The teacher bookmarks the longer one once.
  #
  # See modules/lesson_hosting for the full reasoning and the accepted
  # residual risk.
  lesson_domain_name = "classroom.andreas.services"
  admin_domain_name  = "classroom-admin.andreas.services"

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

# A lesson is a DIRECTORY in this bucket, uploaded by the teacher's browser
# straight to S3 with a presigned URL and served back byte for byte.
module "lessons" {
  source = "../../modules/lessons"

  bucket_name = "${local.name_prefix}-lessons-${local.region}"

  # Only the admin app may PUT. Never "*": a presigned URL is a bearer token in
  # a query string, and CORS is what stops another site's page from using one it
  # somehow obtained.
  upload_origins = ["https://${local.admin_domain_name}"]

  serve_via_cloudfront        = true
  cloudfront_distribution_arn = module.lesson_hosting.distribution_arn

  tags = local.common_tags
}

module "lesson_hosting" {
  source = "../../modules/lesson_hosting"

  # ORDERING, AND IT IS LOAD-BEARING ON THE FIRST APPLY.
  #
  # `classroom.andreas.services` was the APP's CloudFront alias before this
  # split; it is the lesson distribution's now. CloudFront refuses to attach an
  # alias that another distribution still holds (`CNAMEAlreadyExists`), and
  # Terraform infers no dependency between the two distributions — nothing in
  # one references the other — so without this it is free to create this one
  # first and fail.
  #
  # `module.hosting` releases the alias when it moves to `classroom-admin`, so
  # it has to finish first. Harmless on every subsequent apply.
  depends_on = [module.hosting]

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  project     = local.project
  environment = local.environment

  domain_name                         = local.lesson_domain_name
  route53_zone_id                     = data.aws_route53_zone.main.zone_id
  lessons_bucket_regional_domain_name = module.lessons.bucket_regional_domain_name

  tags = local.common_tags
}

module "compute" {
  source = "../../modules/compute"

  project     = local.project
  environment = local.environment

  create_ecr = true

  pages_table_name = module.data.pages_table_name
  pages_table_arn  = module.data.pages_table_arn

  # The API mints presigned PUTs into this bucket and copies objects between the
  # draft and live prefixes on publish, so it needs the name and write access.
  lessons_bucket_name = module.lessons.bucket_id
  lessons_bucket_arn  = module.lessons.bucket_arn

  # Where a share link points — the STUDENT host, not the admin one.
  public_site_url = "https://${local.lesson_domain_name}"

  # Who may call the API from a browser — the ADMIN host, and only that.
  allowed_origin = "https://${local.admin_domain_name}"

  # The API verifies every ID token against this pool and client itself.
  cognito_user_pool_id = module.auth.user_pool_id
  cognito_client_id    = module.auth.user_pool_client_id

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
  # The ADMIN host. Sign-in belongs to the app, and the lesson host never
  # authenticates anyone — that is the whole point of separating them.
  callback_urls = [
    "https://${local.admin_domain_name}/auth/callback",
    "http://localhost:5174/auth/callback",
  ]
  logout_urls = [
    "https://${local.admin_domain_name}/",
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

  domain_name                    = local.admin_domain_name
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

resource "aws_ssm_parameter" "cognito_user_pool_id" {
  name  = "/${local.project}/${local.environment}/cognito-user-pool-id"
  type  = "String"
  value = module.auth.user_pool_id
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
