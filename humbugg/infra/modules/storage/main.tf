resource "aws_s3_bucket" "frontend" {
  bucket = "${var.project}-web-${var.environment}"

  tags = var.tags
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_dynamodb_table" "profiles" {
  name         = "${var.project}-profiles"
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
  name         = "${var.project}-groups"
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
  name         = "${var.project}-groupmembers"
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
  name         = "${var.project}-draws"
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
  name         = "${var.project}-audit-events"
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

resource "aws_dynamodb_table" "email_messages" {
  name         = "${var.project}-email-messages"
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
