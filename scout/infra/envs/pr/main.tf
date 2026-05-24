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

resource "aws_dynamodb_table" "events" {
  name         = "scout-events-pr-${var.pr_number}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "event_id"

  attribute {
    name = "event_id"
    type = "S"
  }

  server_side_encryption { enabled = true }
  tags = local.common_tags
}

resource "aws_dynamodb_table" "emails" {
  name         = "scout-emails-pr-${var.pr_number}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "email_id"

  attribute {
    name = "email_id"
    type = "S"
  }

  server_side_encryption { enabled = true }
  tags = local.common_tags
}

resource "aws_dynamodb_table" "senders" {
  name         = "scout-senders-pr-${var.pr_number}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "sender_key"

  attribute {
    name = "sender_key"
    type = "S"
  }

  server_side_encryption { enabled = true }
  tags = local.common_tags
}

resource "aws_dynamodb_table" "regions" {
  name         = "scout-regions-pr-${var.pr_number}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "slug"

  attribute {
    name = "slug"
    type = "S"
  }

  server_side_encryption { enabled = true }
  tags = local.common_tags
}

resource "aws_dynamodb_table" "categories" {
  name         = "scout-categories-pr-${var.pr_number}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "slug"

  attribute {
    name = "slug"
    type = "S"
  }

  server_side_encryption { enabled = true }
  tags = local.common_tags
}

module "compute" {
  source = "../../modules/compute"

  pr_number                 = var.pr_number
  table_suffix              = "-pr-${var.pr_number}"
  email_processor_image_uri = var.email_processor_image_uri
  events_api_image_uri      = var.events_api_image_uri
  create_ecr                = false
  create_eventbridge        = false

  email_processor_env_vars = {
    ANTHROPIC_API_KEY   = var.anthropic_api_key
    GMAIL_CLIENT_ID     = var.gmail_client_id
    GMAIL_CLIENT_SECRET = var.gmail_client_secret
    GMAIL_REFRESH_TOKEN = var.gmail_refresh_token
    MAX_EMAILS_PER_RUN  = tostring(var.max_emails_per_run)
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
