resource "aws_dynamodb_table" "profiles" {
  name         = "${var.resource_prefix}-profiles"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  attribute {
    name = "user_id"
    type = "S"
  }
  server_side_encryption { enabled = true }
  tags = var.tags
}

resource "aws_dynamodb_table" "groups" {
  name         = "${var.resource_prefix}-groups"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "group_id"
  attribute {
    name = "group_id"
    type = "S"
  }
  server_side_encryption { enabled = true }
  tags = var.tags
}

resource "aws_dynamodb_table" "groupmembers" {
  name         = "${var.resource_prefix}-groupmembers"
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
  tags = var.tags
}

resource "aws_dynamodb_table" "draws" {
  name         = "${var.resource_prefix}-draws"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "group_id"
  attribute {
    name = "group_id"
    type = "S"
  }
  server_side_encryption { enabled = true }
  tags = var.tags
}

resource "aws_dynamodb_table" "audit_events" {
  name         = "${var.resource_prefix}-audit-events"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "group_id"
  range_key    = "event_id"
  attribute {
    name = "group_id"
    type = "S"
  }
  attribute {
    name = "event_id"
    type = "S"
  }
  server_side_encryption { enabled = true }
  tags = var.tags
}

resource "aws_dynamodb_table" "analytics_events" {
  name         = "${var.resource_prefix}-analytics-events"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "idempotency_key"
  attribute {
    name = "idempotency_key"
    type = "S"
  }
  server_side_encryption { enabled = true }
  tags = var.tags
}

resource "aws_dynamodb_table" "email_messages" {
  name         = "${var.resource_prefix}-email-messages"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "message_id"
  attribute {
    name = "message_id"
    type = "S"
  }
  server_side_encryption { enabled = true }
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
  tags = var.tags
}

resource "aws_dynamodb_table" "billing" {
  name         = "${var.resource_prefix}-billing"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "record_id"
  attribute {
    name = "record_id"
    type = "S"
  }
  attribute {
    name = "group_id"
    type = "S"
  }

  global_secondary_index {
    name            = "group_id-index"
    hash_key        = "group_id"
    projection_type = "ALL"
  }

  server_side_encryption { enabled = true }
  tags = var.tags
}

resource "aws_dynamodb_table" "invitations" {
  name         = "${var.resource_prefix}-invitations"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "invitation_id"
  attribute {
    name = "invitation_id"
    type = "S"
  }
  attribute {
    name = "group_id"
    type = "S"
  }

  global_secondary_index {
    name            = "group_id-index"
    hash_key        = "group_id"
    projection_type = "ALL"
  }

  server_side_encryption { enabled = true }
  tags = var.tags
}

resource "aws_s3_bucket" "app" {
  bucket        = var.app_bucket_name
  force_destroy = true
  tags          = var.tags
}

resource "aws_s3_bucket_public_access_block" "app" {
  bucket = aws_s3_bucket.app.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "app" {
  bucket = aws_s3_bucket.app.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "app" {
  bucket = aws_s3_bucket.app.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
