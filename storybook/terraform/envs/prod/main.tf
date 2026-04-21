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

  # All DynamoDB table ARNs, passed into the compute module for IAM policy
  dynamodb_table_arns = {
    user_profiles      = aws_dynamodb_table.user_profiles.arn
    child_profiles     = aws_dynamodb_table.child_profiles.arn
    story_projects     = aws_dynamodb_table.story_projects.arn
    story_pages        = aws_dynamodb_table.story_pages.arn
    chat_messages      = aws_dynamodb_table.chat_messages.arn
    character_assets   = aws_dynamodb_table.character_assets.arn
    story_states       = aws_dynamodb_table.story_states.arn
    images             = aws_dynamodb_table.images.arn
    model_projects     = aws_dynamodb_table.model_projects.arn
    generation_history = aws_dynamodb_table.generation_history.arn
    training_runs      = aws_dynamodb_table.training_runs.arn
  }
}

# Route53 hosted zone (shared, managed outside Terraform)
data "aws_route53_zone" "main" {
  name         = "andreas.services"
  private_zone = false
}

# ─── DynamoDB Tables ──────────────────────────────────────────────────────────

resource "aws_dynamodb_table" "user_profiles" {
  name         = "storybook-user-profiles"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  attribute { name = "user_id"; type = "S" }
  server_side_encryption { enabled = true }
  tags = local.common_tags
}

resource "aws_dynamodb_table" "child_profiles" {
  name         = "storybook-child-profiles"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "profile_id"
  attribute { name = "profile_id"; type = "S" }
  attribute { name = "project_id"; type = "S" }
  global_secondary_index {
    name            = "project_id-index"
    hash_key        = "project_id"
    projection_type = "ALL"
  }
  server_side_encryption { enabled = true }
  tags = local.common_tags
}

resource "aws_dynamodb_table" "story_projects" {
  name         = "storybook-story-projects"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "project_id"
  attribute { name = "project_id"; type = "S" }
  attribute { name = "user_id";    type = "S" }
  attribute { name = "created_at"; type = "S" }
  global_secondary_index {
    name            = "user_id-created_at-index"
    hash_key        = "user_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }
  server_side_encryption { enabled = true }
  tags = local.common_tags
}

resource "aws_dynamodb_table" "story_pages" {
  name         = "storybook-story-pages"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "page_id"
  attribute { name = "page_id";     type = "S" }
  attribute { name = "project_id";  type = "S" }
  attribute { name = "page_number"; type = "N" }
  global_secondary_index {
    name            = "project_id-page_number-index"
    hash_key        = "project_id"
    range_key       = "page_number"
    projection_type = "ALL"
  }
  server_side_encryption { enabled = true }
  tags = local.common_tags
}

resource "aws_dynamodb_table" "chat_messages" {
  name         = "storybook-chat-messages"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "message_id"
  attribute { name = "message_id"; type = "S" }
  attribute { name = "project_id"; type = "S" }
  attribute { name = "sequence";   type = "S" }
  global_secondary_index {
    name            = "project_id-sequence-index"
    hash_key        = "project_id"
    range_key       = "sequence"
    projection_type = "ALL"
  }
  server_side_encryption { enabled = true }
  tags = local.common_tags
}

resource "aws_dynamodb_table" "character_assets" {
  name         = "storybook-character-assets"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "asset_id"
  attribute { name = "asset_id";   type = "S" }
  attribute { name = "project_id"; type = "S" }
  attribute { name = "created_at"; type = "S" }
  global_secondary_index {
    name            = "project_id-created_at-index"
    hash_key        = "project_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }
  server_side_encryption { enabled = true }
  tags = local.common_tags
}

resource "aws_dynamodb_table" "story_states" {
  name         = "storybook-story-states"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "state_id"
  attribute { name = "state_id";   type = "S" }
  attribute { name = "project_id"; type = "S" }
  attribute { name = "version";    type = "N" }
  global_secondary_index {
    name            = "project_id-version-index"
    hash_key        = "project_id"
    range_key       = "version"
    projection_type = "ALL"
  }
  server_side_encryption { enabled = true }
  tags = local.common_tags
}

resource "aws_dynamodb_table" "images" {
  name         = "storybook-images"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "image_id"
  attribute { name = "image_id";   type = "S" }
  attribute { name = "project_id"; type = "S" }
  attribute { name = "created_at"; type = "S" }
  global_secondary_index {
    name            = "project_id-created_at-index"
    hash_key        = "project_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }
  server_side_encryption { enabled = true }
  tags = local.common_tags
}

resource "aws_dynamodb_table" "model_projects" {
  name         = "storybook-model-projects"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "project_id"
  attribute { name = "project_id"; type = "S" }
  attribute { name = "user_id";    type = "S" }
  attribute { name = "created_at"; type = "S" }
  global_secondary_index {
    name            = "user_id-created_at-index"
    hash_key        = "user_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }
  server_side_encryption { enabled = true }
  tags = local.common_tags
}

resource "aws_dynamodb_table" "generation_history" {
  name         = "storybook-generation-history"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "generation_id"
  attribute { name = "generation_id"; type = "S" }
  attribute { name = "project_id";    type = "S" }
  attribute { name = "created_at";    type = "S" }
  global_secondary_index {
    name            = "project_id-created_at-index"
    hash_key        = "project_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }
  server_side_encryption { enabled = true }
  tags = local.common_tags
}

resource "aws_dynamodb_table" "training_runs" {
  name         = "storybook-training-runs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "training_run_id"
  attribute { name = "training_run_id"; type = "S" }
  attribute { name = "project_id";      type = "S" }
  attribute { name = "created_at";      type = "S" }
  global_secondary_index {
    name            = "project_id-created_at-index"
    hash_key        = "project_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }
  server_side_encryption { enabled = true }
  tags = local.common_tags
}

# ─── Auth ─────────────────────────────────────────────────────────────────────

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

# ─── Storage ──────────────────────────────────────────────────────────────────

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

# ─── Image Queue ──────────────────────────────────────────────────────────────

module "image_queue" {
  source = "../../modules/image_queue"

  project     = local.project
  environment = local.environment

  tags = local.common_tags
}

# ─── Image Worker ─────────────────────────────────────────────────────────────

module "image_worker" {
  source = "../../modules/image_worker"

  project     = local.project
  environment = local.environment

  s3_bucket_arn = module.storage.backend_files_bucket_arn
  queue_arn     = module.image_queue.queue_arn

  tags = local.common_tags
}

# ─── Compute (Lambda + API Gateway) ───────────────────────────────────────────

module "compute" {
  source = "../../modules/compute"

  project     = local.project
  environment = local.environment
  aws_region  = var.aws_region

  cognito_user_pool_id = module.auth.user_pool_id
  cognito_client_id    = module.auth.user_pool_client_id

  s3_bucket_id        = module.storage.backend_files_bucket_id
  s3_bucket_arn       = module.storage.backend_files_bucket_arn
  image_queue_arn     = module.image_queue.queue_arn
  dynamodb_table_arns = local.dynamodb_table_arns

  cors_allowed_origins = [
    "https://${local.domain_name}",
    "http://localhost:5173"
  ]

  tags = local.common_tags
}

# ─── Hosting (CloudFront + Route53) ───────────────────────────────────────────

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
