terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source = "hashicorp/aws"
      # The major every other module in this service pins, so a standalone
      # `terraform validate` here means the same thing it means next door.
      version = ">= 6.12, < 7.0"
    }
  }
}

# THE SHARED DEV-SEED BUCKET.
#
# One fixture, published once, downloaded per machine (#284, #285). A dev stack
# is empty when `dev-aws-setup.sh` finishes; `dev-aws-seed.sh` fills it from
# here, so `dev-up.sh` shows a library that looks like the product instead of a
# blank page.
#
#   v1/catalog.json   the node tree — names, kinds, parents, source key per file
#   v1/manifest.json  version, object count, total bytes, per-object checksums
#   v1/media/…        the fixture bytes
#
# `v1/` is a version PREFIX, not object versioning: a fixture change is additive
# and a machine can be re-seeded to a known revision by naming `v2/`. Object
# versioning below answers a different question — see it.
#
# **This bucket is not per machine, and that is the whole of its value.** Every
# developer's stack is seeded from the same bytes, so "works on my machine"
# stops being a statement about which media happened to be lying around. A
# per-machine copy would be N copies of a fixture that never changes.
#
# Contents are real model output promoted out of a developer's dev stack, never
# a copy of anyone's production library. That is what makes it shareable at all,
# and it is enforced upstream rather than here, in two places: `dev_seed.source()`
# refuses to read a bucket or table named `*prod*` at all, and `name_problems`
# refuses a tree that was not driven with names in `DEV_SUBJECTS`. `catalog.json`
# lands in git, and hard rule #1 applies to it in its env-scoped form — a dev
# subject may be named there, a production character may not.

# `force_destroy` is deliberately ABSENT, and the absence is the decision.
#
# This bucket outlives every dev stack that reads it — `dev-aws-destroy.sh` must
# never be able to reach it, which is also why it is not declared in `envs/dev`
# at all. It holds the only copy of a fixture someone curated by hand: there is
# no upstream to re-fetch it from, and re-curating it means driving a dev stack
# through a session of generations again, which costs money.
#
# The root CLAUDE.md's rule is that `force_destroy` must be set at CREATION or
# never, because Terraform applies the destroy half of a replacement against
# prior state and never reads a flag added in the same apply as the rename. So
# this is the one and only moment the decision can be made, and the cost of
# making it this way is stated rather than discovered: renaming this bucket
# later is an out-of-band empty-then-delete, not a Terraform change.
resource "aws_s3_bucket" "seed" {
  bucket = var.bucket_name
  tags   = var.tags

  # `terraform destroy` on whichever root owns this fails by design, exactly as
  # it does for the prod media bucket. That is the point: a fixture nobody can
  # regenerate for free should not come off the back of a destroy someone ran
  # meaning something else.
  lifecycle {
    prevent_destroy = true
  }
}

# VERSIONED, unlike the dev media buckets it feeds.
#
# `modules/dev_storage` leaves versioning off on purpose — recovery there is
# re-seeding from here, so history would only slow `force_destroy` down and bill
# for bytes nobody restores. This bucket is the thing that justification points
# at, so it must have the property they are allowed to lack.
#
# What it protects against is a bad promotion overwriting a good fixture in
# place: `v1/media/…` keys are stable across re-publishes of the same version,
# so a mistaken `--apply` replaces bytes rather than adding them. With versioning
# on that is a new version and the previous one is still there. Small enough that
# the history costs nothing.
resource "aws_s3_bucket_versioning" "seed" {
  bucket = aws_s3_bucket.seed.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Disable ACLs — the account that owns the bucket owns every object. Same as
# every other bucket in this service.
resource "aws_s3_bucket_ownership_controls" "seed" {
  bucket = aws_s3_bucket.seed.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# All four public-access blocks on. Nothing here is public: `dev-aws-seed.sh`
# reads it with the developer's own AWS login, and there is no anonymous reader
# and no CloudFront in front of it.
#
# It is worth being explicit about what "read-only to dev machines" does and
# does not mean today. There is ONE human principal in this account, and it both
# publishes and seeds, so no IAM boundary separates the two. What makes a write
# deliberate is the publisher: `studio dev-seed publish` is a dry run unless
# `--apply` and refuses without an explicit attestation. That is a procedural
# guard, not an enforced one, and it becomes an enforced one the day a second
# developer gets an identity of their own — at which point this is where the
# read-only bucket policy goes.
resource "aws_s3_bucket_public_access_block" "seed" {
  bucket                  = aws_s3_bucket.seed.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Encrypted at rest (SSE-S3 / AES256, bucket key on) — free, and it keeps this
# bucket's configuration comparable to the media buckets' where the comparison
# costs nothing.
resource "aws_s3_bucket_server_side_encryption_configuration" "seed" {
  bucket = aws_s3_bucket.seed.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# One lifecycle rule, and only one.
#
# Incomplete multipart uploads are billed and invisible in a listing; a fixture
# carries a video, and a `cp` interrupted partway leaves parts behind forever.
#
# **Noncurrent versions are deliberately NOT expired.** Versioning above exists
# so a bad promotion is recoverable, and a rule that deleted the history after N
# days would quietly remove the recovery on the timescale nobody notices — a
# fixture is touched a few times a year. The bytes are measured in megabytes.
resource "aws_s3_bucket_lifecycle_configuration" "seed" {
  bucket = aws_s3_bucket.seed.id

  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}
