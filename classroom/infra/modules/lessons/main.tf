# WHERE A LESSON'S FILES LIVE.
#
# A page is a DIRECTORY here, not a row in a table. The teacher uploads whatever
# her authoring tool produced — `index.html` plus its images, stylesheets and
# fonts — and it is served back byte for byte. Nothing rewrites it, nothing
# sanitizes it, and the paths inside her HTML resolve because the objects sit at
# the same relative positions she uploaded them in.
#
#   lesson/<page-id>/index.html
#   lesson/<page-id>/images/diagram.png
#
# The key prefix deliberately MATCHES the public URL path (`/lesson/<id>/…`), so
# CloudFront maps a request to an object with no rewriting and no lookup. That
# is the whole reason the page id, not the slug, is in the path: a slug can be
# reissued, an id cannot, and a key that has to be resolved through DynamoDB on
# every image request is a Lambda in the hot path for static files.
resource "aws_s3_bucket" "lessons" {
  bucket = var.bucket_name

  # These objects are the only copy of a teacher's work — the same argument the
  # pages table makes for point-in-time recovery. `force_destroy` is therefore
  # NOT set here, deliberately, unlike the regenerable frontend build bucket.
  tags = var.tags
}

resource "aws_s3_bucket_versioning" "lessons" {
  bucket = aws_s3_bucket.lessons.id

  # Re-uploading a lesson overwrites `index.html` in place. Versioning is what
  # makes that survivable: a teacher who uploads the wrong export over a live
  # lesson has not destroyed the old one.
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "lessons" {
  bucket                  = aws_s3_bucket.lessons.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lessons" {
  bucket = aws_s3_bucket.lessons.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# The browser PUTs straight to S3 with a presigned URL, so this bucket is a
# cross-origin write target for the app's own domain. Without this every upload
# fails the preflight.
#
# **GET is deliberately absent.** Students never read from this bucket directly;
# they read through CloudFront, which is same-origin with the app and needs no
# CORS at all. Only the teacher's upload needs a cross-origin verb.
resource "aws_s3_bucket_cors_configuration" "lessons" {
  bucket = aws_s3_bucket.lessons.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT"]
    allowed_origins = var.upload_origins
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

# Read is CloudFront's, and only through the distribution that owns the OAC.
#
# `envs/dev` passes no distribution — a per-machine CloudFront would cost twenty
# minutes an apply to prove nothing — so there is no bucket policy there at all.
# The local API reads lessons with the developer's own IAM credentials instead,
# which is the same arrangement `dev-up.sh` uses for everything else.
data "aws_iam_policy_document" "cloudfront_read" {
  count = var.serve_via_cloudfront ? 1 : 0

  statement {
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.lessons.arn}/*"]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [var.cloudfront_distribution_arn]
    }
  }
}

resource "aws_s3_bucket_policy" "lessons" {
  count = var.serve_via_cloudfront ? 1 : 0

  bucket = aws_s3_bucket.lessons.id
  policy = data.aws_iam_policy_document.cloudfront_read[0].json
}
