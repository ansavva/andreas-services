locals {
  project     = "humbugg"
  environment = "production"
  domain_name = "humbugg.andreas.services"

  common_tags = {
    Project     = local.project
    Environment = local.environment
    ManagedBy   = "Terraform"
  }

  dynamodb_table_arns = {
    profiles     = aws_dynamodb_table.profiles.arn
    groups       = aws_dynamodb_table.groups.arn
    groupmembers = aws_dynamodb_table.groupmembers.arn
  }
}

data "aws_route53_zone" "main" {
  name         = "andreas.services"
  private_zone = false
}

resource "aws_dynamodb_table" "profiles" {
  name         = "humbugg-profiles"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  server_side_encryption { enabled = true }
  tags = local.common_tags
}

resource "aws_dynamodb_table" "groups" {
  name         = "humbugg-groups"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "group_id"

  attribute {
    name = "group_id"
    type = "S"
  }

  server_side_encryption { enabled = true }
  tags = local.common_tags
}

resource "aws_dynamodb_table" "groupmembers" {
  name         = "humbugg-groupmembers"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "member_id"

  attribute {
    name = "member_id"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "group_id"
    type = "S"
  }

  global_secondary_index {
    name            = "user_id-index"
    hash_key        = "user_id"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "group_id-index"
    hash_key        = "group_id"
    projection_type = "ALL"
  }

  server_side_encryption { enabled = true }
  tags = local.common_tags
}

module "auth" {
  source = "../../modules/auth"

  project     = local.project
  environment = local.environment

  tags = local.common_tags
}

module "storage" {
  source = "../../modules/storage"

  project     = local.project
  environment = local.environment
  bucket_name = "humbugg-frontend-prod"

  tags = local.common_tags
}

import {
  to = module.compute.aws_ecr_repository.backend
  id = "humbugg-backend-production"
}

module "compute" {
  source = "../../modules/compute"

  project     = local.project
  environment = local.environment

  dynamodb_table_arns = local.dynamodb_table_arns

  tags = local.common_tags
}

module "hosting" {
  source = "../../modules/hosting"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  project     = local.project
  domain_name = local.domain_name

  route53_zone_id = data.aws_route53_zone.main.zone_id

  frontend_bucket_id                   = module.storage.bucket_id
  frontend_bucket_arn                  = module.storage.bucket_arn
  frontend_bucket_regional_domain_name = module.storage.bucket_regional_domain_name

  api_endpoint = module.compute.api_endpoint

  tags = local.common_tags
}
