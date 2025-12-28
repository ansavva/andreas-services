# envs/prod/main.tf
# Production environment - full infrastructure stack

locals {
  project     = "storybook"
  environment = "production"
  domain_name = "storybook.andreas.services"

  common_tags = {
    Project     = local.project
    Environment = local.environment
    ManagedBy   = "Terraform"
    Region      = var.aws_region
  }
}

# Shared infrastructure state (VPC, DocDB, etc.)
data "terraform_remote_state" "shared" {
  backend = "s3"
  config = {
    bucket = "andreas-services-terraform-state"
    key    = "shared/terraform.tfstate"
    region = "us-east-1"
  }
}

# Data source for Route53 hosted zone
data "aws_route53_zone" "main" {
  name         = "andreas.services"
  private_zone = false
}

# Auth module - Cognito
module "auth" {
  source = "../../modules/auth"

  project     = local.project
  environment = local.environment

  callback_urls = [
    "https://${local.domain_name}/app",
    "http://localhost:5173/app"
  ]

  logout_urls = [
    "https://${local.domain_name}/app",
    "http://localhost:5173/app"
  ]

  tags = local.common_tags
}

# Storage module - S3 buckets
module "storage" {
  source = "../../modules/storage"

  project     = local.project
  environment = local.environment

  cors_allowed_origins = [
    "https://${local.domain_name}",
    "http://localhost:5173"
  ]

  create_frontend_bucket = true

  tags = local.common_tags
}

# Compute module - Lambda + API Gateway
module "compute" {
  source = "../../modules/compute"

  project     = local.project
  environment = local.environment
  aws_region  = var.aws_region
  enable_vpc  = true
  vpc_id      = data.terraform_remote_state.shared.outputs.shared_vpc_id
  subnet_ids  = data.terraform_remote_state.shared.outputs.shared_private_subnet_ids

  cognito_user_pool_id = module.auth.user_pool_id
  cognito_client_id    = module.auth.user_pool_client_id

  s3_bucket_id  = module.storage.backend_files_bucket_id
  s3_bucket_arn = module.storage.backend_files_bucket_arn

  cors_allowed_origins = [
    "https://${local.domain_name}",
    "http://localhost:5173"
  ]

  tags = local.common_tags
}

# Allow Lambda access to shared DocumentDB
resource "aws_security_group_rule" "lambda_to_docdb" {
  type                     = "ingress"
  from_port                = 27017
  to_port                  = 27017
  protocol                 = "tcp"
  security_group_id        = data.terraform_remote_state.shared.outputs.shared_docdb_security_group_id
  source_security_group_id = module.compute.lambda_security_group_id
  description              = "Allow Lambda access to shared DocumentDB"
}

# Hosting module - CloudFront + Route53
module "hosting" {
  source = "../../modules/hosting"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  project     = local.project
  domain_name = local.domain_name

  route53_zone_id = data.aws_route53_zone.main.zone_id

  frontend_bucket_id                   = module.storage.frontend_bucket_id
  frontend_bucket_arn                  = module.storage.frontend_bucket_arn
  frontend_bucket_regional_domain_name = module.storage.frontend_bucket_regional_domain_name

  api_gateway_endpoint = module.compute.api_gateway_endpoint

  tags = local.common_tags
}
