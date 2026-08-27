terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source = "hashicorp/aws"
      # Pinned to the major `envs/dev` pins, as `modules/media` and
      # `modules/catalog` are, so a standalone `terraform validate` here sees
      # the provider the environment actually uses. That major is 6 since
      # Managed Login — `modules/auth`'s branding resource does not exist
      # before 6.12.0; see `envs/prod/providers.tf`.
      version = ">= 6.12, < 7.0"
    }
  }
}

# THE DISPOSABLE HALF OF STUDIO'S STORAGE.
#
# This module is `modules/media` + `modules/catalog` with every guard removed.
# It exists because the guards cannot be made conditional: `prevent_destroy`
# takes a literal, not a variable, so a bucket that `dev-aws-destroy.sh` can
# actually delete cannot come from the module that protects the prod one. The
# alternative — a `count`/`for_each` fork inside `modules/media` — would put the
# prod bucket's protection one wrong variable away from being off, which is the
# trade this module refuses. humbugg has a `dev_storage` for the same reason.
#
# Everything here is per-machine and reconstructible: the bytes come back from
# the seed bucket, the rows from a seed run. Nothing in it is worth a backup and
# nothing in it may resist a teardown.

# The dev media bucket. Same posture as the prod one — private, ACLs off,
# encrypted — minus the two things that make prod's undeletable.
#
# `force_destroy` is set HERE, at creation, and must never be retrofitted. Per
# the root CLAUDE.md: Terraform applies the destroy half of a replacement
# against prior state, so the provider reads the flag recorded in state and
# never sees a `true` added in the same apply as the rename. A dev bucket that
# picks up objects before it picks up the flag is a bucket only an out-of-band
# empty-then-delete can remove.
resource "aws_s3_bucket" "media" {
  bucket        = var.media_bucket_name
  force_destroy = true
  tags          = var.tags
}

# Disable ACLs — the account that owns the bucket owns every object.
resource "aws_s3_bucket_ownership_controls" "media" {
  bucket = aws_s3_bucket.media.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Block all public access. The local backend hands objects to the browser as
# short-lived presigned URLs exactly as the deployed one does, and those work
# with every one of these flags on.
resource "aws_s3_bucket_public_access_block" "media" {
  bucket                  = aws_s3_bucket.media.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Encrypted at rest (SSE-S3 / AES256, bucket key on) — free, and it keeps the
# dev bucket's configuration comparable to prod's where the comparison costs
# nothing.
resource "aws_s3_bucket_server_side_encryption_configuration" "media" {
  bucket = aws_s3_bucket.media.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# CORS, and this one IS a copy of prod's rather than a relaxation of it.
#
# The upload is a presigned PUT sent by the browser straight to the bucket, so it
# preflights, and a dev bucket without this rule fails every upload locally while
# prod works — the worst shape a difference between the two can take. The rule is
# the same three lines as `modules/media`, which documents each of them; only the
# origin differs, and it is Vite's rather than the deployed SPA's.
#
# It agrees with `dev-up.sh`, which exports `STUDIO_ALLOWED_ORIGIN` as
# `http://localhost:5173` — one spelling, not also `127.0.0.1`. Allowing a second
# loopback spelling here would mean an origin S3 accepts and the API rejects,
# which turns one legible CORS failure into two halves of one.
resource "aws_s3_bucket_cors_configuration" "media" {
  bucket = aws_s3_bucket.media.id

  cors_rule {
    allowed_methods = ["PUT"]
    allowed_origins = var.cors_allowed_origins
    allowed_headers = ["content-type", "content-length"]
    max_age_seconds = 3600
  }
}

# No `aws_s3_bucket_versioning` here, deliberately. On the prod bucket
# versioning is load-bearing: curate rewrites objects in place and tidy-up
# deletes them, and a role without `s3:DeleteObjectVersion` is what makes both
# recoverable. Here the recovery is `dev-aws-reset.sh` — re-seed from
# `studio-dev-seed-us-east-1` — so version history would only slow the teardown
# down (`force_destroy` has to delete every version) and bill for bytes nobody
# will ever restore.

# The dev catalog table.
#
# The key schema and the three indexes are a deliberate, exact copy of
# `modules/catalog` — same `pk`/`sk`, same `by-sk`, `by-path` and `by-recent`,
# all `ALL`-projected. That duplication is the cost of the `prevent_destroy`
# split above and it is load-bearing: an index missing here is a query that
# passes locally and fails in prod, or the reverse. If this ever drifts from
# `modules/catalog`, that module is the source of truth — mirror it back.
#
# `modules/catalog` documents why each of these exists; the reasoning is not
# repeated here so there is only one place to correct it.
#
# What differs from prod is only what protects the data, because there is no
# data here worth protecting:
#   - PITR off. It is prod's only recovery from a bad transaction. These rows
#     are fixtures written by the seed script and re-writable at any time.
#   - Deletion protection off. `dev-aws-destroy.sh` must be able to complete in
#     one pass; a table needing a manual disable first is a teardown people stop
#     running.
resource "aws_dynamodb_table" "catalog" {
  name         = var.catalog_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  # Key attributes only, as in `modules/catalog` — declaring a non-key
  # attribute is an error, not a no-op.
  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  attribute {
    name = "lib"
    type = "S"
  }

  attribute {
    name = "path"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  # The reel's partition key. Its value is the library id, but the *name* is
  # what makes `by-recent` sparse — see `modules/catalog`, which explains why.
  attribute {
    name = "reel"
    type = "S"
  }

  # Reverse lookup — "who is in library X".
  global_secondary_index {
    name            = "by-sk"
    hash_key        = "sk"
    range_key       = "pk"
    projection_type = "ALL"
  }

  # Recursive subtree listing over materialised ancestor ids.
  global_secondary_index {
    name            = "by-path"
    hash_key        = "lib"
    range_key       = "path"
    projection_type = "ALL"
  }

  # Newest/oldest across a library, genuinely paginated. Sparse on `reel`.
  global_secondary_index {
    name            = "by-recent"
    hash_key        = "reel"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  # Selects the AWS-managed `aws/dynamodb` key over the AWS-owned default.
  # Free, and it keeps the dev table auditable in KMS like the prod one.
  server_side_encryption {
    enabled = true
  }

  point_in_time_recovery {
    enabled = false
  }

  deletion_protection_enabled = false

  tags = var.tags
}
