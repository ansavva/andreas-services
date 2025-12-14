# modules/storage/main.tf
# S3 buckets for frontend and backend file storage

# Backend files bucket (both dev and prod)
resource "aws_s3_bucket" "backend_files" {
  bucket = "${var.project}-backend-files-${var.environment}"

  tags = var.tags
}

resource "aws_s3_bucket_public_access_block" "backend_files" {
  bucket = aws_s3_bucket.backend_files.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "backend_files" {
  bucket = aws_s3_bucket.backend_files.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backend_files" {
  bucket = aws_s3_bucket.backend_files.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "backend_files" {
  bucket = aws_s3_bucket.backend_files.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST", "DELETE"]
    allowed_origins = var.cors_allowed_origins
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

# Frontend bucket (optional - prod only)
resource "aws_s3_bucket" "frontend" {
  count  = var.create_frontend_bucket ? 1 : 0
  bucket = "${var.project}-frontend-${var.environment}"

  tags = var.tags
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  count  = var.create_frontend_bucket ? 1 : 0
  bucket = aws_s3_bucket.frontend[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "frontend" {
  count  = var.create_frontend_bucket ? 1 : 0
  bucket = aws_s3_bucket.frontend[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  count  = var.create_frontend_bucket ? 1 : 0
  bucket = aws_s3_bucket.frontend[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
