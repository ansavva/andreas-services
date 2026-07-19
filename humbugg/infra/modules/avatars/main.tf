# Dedicated bucket for user profile photos. Objects are written only by the backend Lambda (via the
# least-privilege policy attached in the compute module) and read only by CloudFront through Origin
# Access Control (wired in the hosting module). The bucket itself is fully private — no public ACLs,
# no public policy — so an avatar is never world-readable or world-writable at the S3 layer.
resource "aws_s3_bucket" "avatars" {
  bucket = "${var.project}-avatars-${var.environment}"

  tags = var.tags
}

resource "aws_s3_bucket_public_access_block" "avatars" {
  bucket = aws_s3_bucket.avatars.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Enforce bucket-owner ownership and disable ACLs entirely, so access is governed only by the bucket
# policy (CloudFront OAC) and IAM — never by object ACLs.
resource "aws_s3_bucket_ownership_controls" "avatars" {
  bucket = aws_s3_bucket.avatars.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "avatars" {
  bucket = aws_s3_bucket.avatars.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "avatars" {
  bucket = aws_s3_bucket.avatars.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Replacing an avatar writes a new key and clears the old one, so noncurrent versions accumulate.
# Expire them after 30 days to keep the bucket small while retaining a short recovery window.
resource "aws_s3_bucket_lifecycle_configuration" "avatars" {
  bucket = aws_s3_bucket.avatars.id

  rule {
    id     = "expire-noncurrent-avatars"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 30
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# CORS so a browser can display the avatar image cross-origin if ever served from a different host
# than the page. Read-only methods only; write access is never granted to browsers.
resource "aws_s3_bucket_cors_configuration" "avatars" {
  bucket = aws_s3_bucket.avatars.id

  cors_rule {
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = ["https://${var.domain_name}"]
    allowed_headers = ["*"]
    max_age_seconds = 3600
  }
}
