locals {
  project     = "scout"
  environment = "production"
  domain_name = "scout.andreas.services"

  common_tags = {
    Project     = local.project
    Environment = local.environment
    ManagedBy   = "Terraform"
  }
}

data "aws_route53_zone" "main" {
  name         = "andreas.services"
  private_zone = false
}

resource "aws_dynamodb_table" "events" {
  name         = "scout-events"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "event_id"

  attribute {
    name = "event_id"
    type = "S"
  }

  server_side_encryption { enabled = true }
  tags = local.common_tags
}

module "storage" {
  source = "../../modules/storage"

  bucket_name = "scout-static-prod"

  tags = local.common_tags
}

import {
  to = module.compute.aws_ecr_repository.email_processor[0]
  id = "scout-email-processor"
}

import {
  to = module.compute.aws_ecr_repository.events_api[0]
  id = "scout-events-api"
}

import {
  to = module.hosting.aws_cloudfront_function.spa_fallback
  id = "scout-spa-fallback"
}

module "compute" {
  source = "../../modules/compute"

  dynamodb_table_arn = aws_dynamodb_table.events.arn
  events_table_name  = aws_dynamodb_table.events.name
  create_ecr         = true
  create_eventbridge = true

  email_processor_env_vars = {
    ANTHROPIC_API_KEY   = var.anthropic_api_key
    GMAIL_CLIENT_ID     = var.gmail_client_id
    GMAIL_CLIENT_SECRET = var.gmail_client_secret
    GMAIL_REFRESH_TOKEN = var.gmail_refresh_token
    MAX_EMAILS_PER_RUN  = "20"
    DYNAMODB_TABLE_NAME = aws_dynamodb_table.events.name
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

module "api_gateway" {
  source = "../../modules/api_gateway"

  lambda_invoke_arn    = module.compute.events_api_invoke_arn
  lambda_function_name = module.compute.events_api_function_name
  custom_domain_name   = module.api_domain.domain_name
  base_path            = ""
  stage_name           = "prod"
  throttle_rate        = 10
  throttle_burst       = 50

  tags = local.common_tags
}

module "hosting" {
  source = "../../modules/hosting"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  domain_name         = local.domain_name
  route53_zone_id     = data.aws_route53_zone.main.zone_id
  s3_website_endpoint = module.storage.website_endpoint

  tags = local.common_tags
}
