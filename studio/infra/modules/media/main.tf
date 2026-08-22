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

# CORS, and it exists for exactly ONE request: the presigned PUT a browser sends
# when someone uploads into a folder (#294). That PUT is cross-origin, it carries
# a `Content-Type` S3 has to be told to accept, and so it preflights — without a
# rule here the browser never sends the body and the upload fails with no status
# attached. Reads need nothing: the app draws media with `<img src>` and
# `<video src>`, and plain media loading is not subject to CORS at all.
#
# Deliberately narrow, on all four axes:
#
#   * PUT only. GET is not here because nothing fetches this bucket with `fetch`
#     — `GET /api/text` is served through the API precisely so a second CORS
#     surface would not have to agree with the API's own (see
#     `docs/WEB_APP.md`). Adding a method here means adding it there too.
#   * `content-type` and `content-length` only, because those are exactly the two
#     `s3.presign_put` puts in `X-Amz-SignedHeaders`. A client sending anything
#     else fails signature validation and writes nothing, so a wider list would
#     grant nothing and only blur what the signature actually covers. Note
#     `content-length` never appears in a preflight — it is a forbidden header
#     name, so the browser sets it itself and script cannot — and it is listed
#     anyway so this rule and the signature read the same.
#   * No `expose_headers`. The uploader reads the PUT's *status* and nothing
#     else; `confirm-upload` learns the size from `HeadObject` server-side rather
#     than from an `ETag` the browser would have to be allowed to see.
#   * Origins from the caller. There is no `*` here and there must not be: a
#     wildcard would let any page a signed-in user visits complete a PUT whose
#     URL it had somehow obtained.
resource "aws_s3_bucket_cors_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  cors_rule {
    allowed_methods = ["PUT"]
    allowed_origins = var.cors_allowed_origins
    allowed_headers = ["content-type", "content-length"]
    max_age_seconds = 3600
  }
}
