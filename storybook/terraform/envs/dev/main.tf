# envs/dev/main.tf
# Development environment - minimal resources for local development

locals {
  project     = "storybook"
  environment = "development"

  common_tags = {
    Project     = local.project
    Environment = local.environment
    ManagedBy   = "Terraform"
    Region      = var.aws_region
  }
}

# Auth module - Cognito for local dev
module "auth" {
  source = "../../modules/auth"

  project     = local.project
  environment = local.environment

  callback_urls = [
    "http://localhost:5173" # Local frontend only
  ]

  logout_urls = [
    "http://localhost:5173"
  ]

  tags = local.common_tags
}

# Storage bucket for dev uploads
module "storage" {
  source = "../../modules/storage"

  project     = local.project
  environment = local.environment

  cors_allowed_origins = [
    "http://localhost:5173"
  ]

  create_frontend_bucket = false

  tags = local.common_tags
}

# Image normalization queue (dev)
module "image_queue" {
  source = "../../modules/image_queue"

  project     = local.project
  environment = local.environment

  tags = local.common_tags
}

# No compute module in dev - backend runs locally
# No hosting module in dev - no CloudFront/Route53 needed
