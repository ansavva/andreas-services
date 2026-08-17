terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# The media bucket — the canonical asset store for the whole of studio. The
# generation skills write characters, runs, scenes and movies into it; the API
# reads it back out. It is the only thing in this service holding data that
# cannot be rebuilt from source.
#
# `prevent_destroy` is here because of that. Around 700 MB of generated media
# lives in this bucket with no second copy anywhere, and Terraform's default
# posture — replace on any name change, destroy on `terraform destroy` — is the
# wrong one for it. Note the blast radius: this blocks `terraform destroy` on
# the ENTIRE studio/prod state, which is intended. Genuinely tearing studio down
# means removing this module from state first, deliberately.
#
# There is no `force_destroy` either. S3 refuses to delete a non-empty bucket
# without it, so the two together mean a delete has to be argued for twice.
resource "aws_s3_bucket" "this" {
  bucket = var.bucket_name
  tags   = var.tags

  lifecycle {
    prevent_destroy = true
  }
}

# Disable ACLs — the account that owns the bucket owns every object.
resource "aws_s3_bucket_ownership_controls" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Block all public access. The bucket hands objects out as short-lived presigned
# URLs — to Replicate from the skills, to the browser from the API — and those
# keep working with every one of these flags on. Nothing here is ever public.
resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.this.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Versioning is load-bearing, not hygiene. Curating a character rewrites objects
# in place and the app's tidy-up actions delete them; both are recoverable only
# because prior revisions survive.
resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id
  versioning_configuration {
    status = var.versioning_enabled ? "Enabled" : "Suspended"
  }
}

# Server-side encryption at rest (SSE-S3 / AES256 — free, always-on).
resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}
