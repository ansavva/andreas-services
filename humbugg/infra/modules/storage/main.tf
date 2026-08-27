resource "aws_s3_bucket" "marketing" {
  bucket = "${var.project}-${var.environment}-marketing-${var.aws_region}"

  tags = var.tags
}

resource "aws_s3_bucket_public_access_block" "marketing" {
  bucket = aws_s3_bucket.marketing.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "marketing" {
  bucket = aws_s3_bucket.marketing.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "marketing" {
  bucket = aws_s3_bucket.marketing.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# The Expo web export for app.humbugg.com. Separate from the `frontend` bucket
# because the two are built by different toolchains on different schedules: this
# one holds a self-contained single-page export, that one holds only the hashed
# assets its SSR Lambda references.
resource "aws_s3_bucket" "app" {
  bucket = "${var.project}-${var.environment}-app-${var.aws_region}"

  tags = var.tags
}

resource "aws_s3_bucket_public_access_block" "app" {
  bucket = aws_s3_bucket.app.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "app" {
  bucket = aws_s3_bucket.app.id

  versioning_configuration {
    status = "Enabled"
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

resource "aws_dynamodb_table" "profiles" {
  name         = "${var.project}-${var.environment}-profiles"
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
  name         = "${var.project}-${var.environment}-groups"
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
  name         = "${var.project}-${var.environment}-groupmembers"
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

# One row per wish, keyed (member_id, wish_id). member_id as the partition key is what makes
# listing a member's wishes a Query rather than a Scan, and what makes every single-item write
# name its owner — there is no way to address a wish without naming the member it belongs to.
# No GSI: every access pattern starts from a known member_id.
resource "aws_dynamodb_table" "wishes" {
  name         = "${var.project}-${var.environment}-wishes"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "member_id"
  range_key    = "wish_id"

  attribute {
    name = "member_id"
    type = "S"
  }

  attribute {
    name = "wish_id"
    type = "S"
  }

  server_side_encryption { enabled = true }
  tags = var.tags
}

resource "aws_dynamodb_table" "draws" {
  name         = "${var.project}-${var.environment}-draws"
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
  name         = "${var.project}-${var.environment}-audit-events"
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

  # The audit trail is append-only and must not silently lose records: enable
  # point-in-time recovery for durability and block accidental table deletion.
  # Records have no TTL — retention is intentionally indefinite (see infra/README.md).
  point_in_time_recovery { enabled = true }
  deletion_protection_enabled = true

  tags = var.tags
}

resource "aws_dynamodb_table" "analytics_events" {
  name         = "${var.project}-${var.environment}-analytics-events"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "idempotency_key"

  attribute {
    name = "idempotency_key"
    type = "S"
  }

  server_side_encryption { enabled = true }

  # Product-analytics events are privacy-safe aggregates (plan + counts only) and are written with
  # an attribute_not_exists condition on idempotency_key, so retries never double-count. Point-in-
  # time recovery lets the internal reporting path export a consistent snapshot; there is no TTL,
  # so the funnel history is retained for trend analysis. See docs/analytics.md.
  point_in_time_recovery { enabled = true }

  tags = var.tags
}

resource "aws_dynamodb_table" "email_messages" {
  name         = "${var.project}-${var.environment}-email-messages"
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

# One-table billing ledger. Payment rows are keyed by a server-generated purchase id;
# Stripe event marker rows share the table and make webhook processing idempotent.
resource "aws_dynamodb_table" "billing" {
  name         = "${var.project}-${var.environment}-billing"
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
  point_in_time_recovery { enabled = true }
  deletion_protection_enabled = true

  tags = var.tags
}

resource "aws_dynamodb_table" "invitations" {
  name         = "${var.project}-${var.environment}-invitations"
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
  point_in_time_recovery { enabled = true }
  tags = var.tags
}

resource "aws_dynamodb_table" "reminders" {
  name         = "${var.project}-${var.environment}-reminders"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "group_id"
  range_key    = "record_key"
  attribute {
    name = "group_id"
    type = "S"
  }
  attribute {
    name = "record_key"
    type = "S"
  }
  server_side_encryption { enabled = true }
  point_in_time_recovery { enabled = true }
  tags = var.tags
}

resource "aws_dynamodb_table" "templates" {
  name         = "${var.project}-${var.environment}-templates"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "template_id"
  attribute {
    name = "user_id"
    type = "S"
  }
  attribute {
    name = "template_id"
    type = "S"
  }
  server_side_encryption { enabled = true }
  point_in_time_recovery { enabled = true }
  tags = var.tags
}

# General-purpose application object bucket. Today it holds user profile photos under the avatars/
# prefix — written only by the backend Lambda (least-privilege policy in the compute module) and read
# only by CloudFront via Origin Access Control on the /avatars/* path — and is the single place for any
# future application objects. Fully private (no public ACLs or policy) so objects are never world-
# readable or world-writable at the S3 layer. Kept separate from the -web- frontend bucket, which the
# deploy syncs with --delete (that would otherwise wipe uploads).
resource "aws_s3_bucket" "app_files" {
  bucket = "${var.project}-${var.environment}-app-files-${var.aws_region}"

  tags = var.tags
}

resource "aws_s3_bucket_public_access_block" "app_files" {
  bucket = aws_s3_bucket.app_files.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Enforce bucket-owner ownership and disable ACLs entirely, so access is governed only by the bucket
# policy (CloudFront OAC) and IAM — never by object ACLs.
resource "aws_s3_bucket_ownership_controls" "app_files" {
  bucket = aws_s3_bucket.app_files.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "app_files" {
  bucket = aws_s3_bucket.app_files.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "app_files" {
  bucket = aws_s3_bucket.app_files.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Replacing an avatar writes a new key and clears the old one, so noncurrent versions accumulate.
# Expire them after 30 days to keep the bucket small while retaining a short recovery window.
resource "aws_s3_bucket_lifecycle_configuration" "app_files" {
  bucket = aws_s3_bucket.app_files.id

  rule {
    id     = "expire-noncurrent-avatars"
    status = "Enabled"

    filter {
      prefix = "avatars/"
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# CORS so a browser can display an avatar image cross-origin if ever served from a different host than
# the page. Read-only methods only; write access is never granted to browsers.
resource "aws_s3_bucket_cors_configuration" "app_files" {
  bucket = aws_s3_bucket.app_files.id

  cors_rule {
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = ["https://${var.domain_name}"]
    allowed_headers = ["*"]
    max_age_seconds = 3600
  }
}
