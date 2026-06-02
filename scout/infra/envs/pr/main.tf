locals {
  project     = "scout"
  environment = "pr-${var.pr_number}"

  common_tags = {
    Project     = local.project
    Environment = local.environment
    ManagedBy   = "Terraform"
    PRNumber    = var.pr_number
  }
}

module "data" {
  source = "../../modules/data"

  table_suffix = "-pr-${var.pr_number}"

  tags = local.common_tags
}

module "artifacts_storage" {
  source = "../../modules/storage"

  bucket_name   = "scout-artifacts-pr-${var.pr_number}"
  force_destroy = true

  tags = local.common_tags
}

module "images_storage" {
  source = "../../modules/storage"

  bucket_name   = "scout-images-pr-${var.pr_number}"
  force_destroy = true

  tags = local.common_tags
}

module "compute" {
  source = "../../modules/compute"

  pr_number            = var.pr_number
  table_suffix         = "-pr-${var.pr_number}"
  events_api_image_uri = var.events_api_image_uri
  renderer_image_uri   = var.renderer_image_uri
  create_ecr           = false
  create_eventbridge   = false

  artifacts_bucket = module.artifacts_storage.bucket_id
  images_bucket    = module.images_storage.bucket_id

  processor_env_vars = {
    ANTHROPIC_API_KEY = var.anthropic_api_key
  }

  tags = local.common_tags
}

module "auth" {
  source = "../../modules/auth"

  name = "scout-pr-${var.pr_number}"
  callback_urls = [
    "https://scout-pr.andreas.services/${var.pr_number}/app",
    "http://localhost:5173/app",
  ]
  logout_urls = [
    "https://scout-pr.andreas.services/${var.pr_number}/app",
    "http://localhost:5173/app",
  ]

  tags = local.common_tags
}

module "api_gateway" {
  source = "../../modules/api_gateway"

  pr_number                 = var.pr_number
  lambda_invoke_arn         = module.compute.events_api_invoke_arn
  lambda_function_name      = module.compute.events_api_function_name
  custom_domain_name        = "scout-api-pr.andreas.services"
  base_path                 = var.pr_number
  stage_name                = "prod"
  throttle_rate             = 5
  throttle_burst            = 20
  cognito_user_pool_arn     = module.auth.user_pool_arn
  enable_cognito_authorizer = true

  tags = local.common_tags
}
