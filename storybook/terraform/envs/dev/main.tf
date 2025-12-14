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

# No storage module in dev - uses local filesystem for files and MongoDB for data
# No compute module in dev - backend runs locally
# No hosting module in dev - no CloudFront/Route53 needed
