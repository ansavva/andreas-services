locals {
  api_name  = "${var.project}-${var.environment}-api"
  api_image = var.create_ecr ? "${aws_ecr_repository.api[0].repository_url}:latest" : var.api_image_uri
}

# ---------------------------------------------------------------------------
# ECR
# ---------------------------------------------------------------------------
# A repository name is immutable, so renaming one is a destroy and recreate, and
# DeleteRepository refuses a repository that still holds images. This holds
# nothing but CI build output the next push rebuilds from git, so there is
# nothing for the guard to protect. Note this only helps the rename AFTER the one
# that introduces it: Terraform applies the destroy half of a replacement against
# prior state, so the flag has to already be recorded there. See "Renaming is a
# destroy-and-recreate" in CLAUDE.md.
resource "aws_ecr_repository" "api" {
  count                = var.create_ecr ? 1 : 0
  name                 = local.api_name
  image_tag_mutability = "MUTABLE"
  force_delete         = true
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "api" {
  count      = var.create_ecr ? 1 : 0
  repository = aws_ecr_repository.api[0].name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}

# ---------------------------------------------------------------------------
# IAM
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "api" {
  name               = "${local.api_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "logs" {
  name = "${local.api_name}-logs"
  role = aws_iam_role.api.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "arn:aws:logs:*:*:*"
    }]
  })
}

# THIS ROLE CAN NOW WRITE, AND THAT IS A DELIBERATE REVERSAL.
#
# For most of studio's life this policy was `ListBucket` + `GetObject` and the
# comment here said so emphatically: the media bucket belongs to the x-harness
# pipeline, studio was a viewer of it, and no bug or compromised token could
# destroy that data because the role simply could not. That was the right
# default and it is worth stating plainly why it changed.
#
# It changed because tidying the library is a thing you do while looking at it.
# A run that produced nothing worth keeping is recognised in the browser, and
# routing "delete these four frames" back through the pipeline meant it never
# happened. So the role gained `PutObject` and `DeleteObject`, scoped to the same
# root the read grants use.
#
# READ THIS BEFORE RELYING ON THAT SCOPE. `media_root_prefix` is now empty —
# x-harness dropped the `media/` wrapper it used to write under, so the
# browsable root is the bucket itself and `${var.media_root_prefix}*` expands to
# `*`. The prefix therefore confines nothing today, and it is a write-capable
# role: what it can read, it can also overwrite and delete. That is a real
# widening of the blast radius over the read-only era, and the only reason it is
# acceptable is that the bucket's entire contents are exactly what studio is for.
# Set the prefix to a real value and both halves narrow again, together.
#
# What still holds the line:
#
#   * `services/keys.py` validates every key and prefix before it reaches boto3,
#     and `assert_inside_root` refuses an operation aimed at the root itself, so
#     "delete everything" is not expressible through the API. With the prefix
#     empty this is the FIRST line of defence, not the second.
#   * There is no multipart grant, and no path that creates an object out of
#     bytes the caller supplied. `PutObject` here writes zero-byte folder
#     markers, overwrites text files that already exist, and lands the
#     destination half of a `CopyObject` — a rename, a move, or a favourite.
#     Every one of those is either something already in the bucket or nothing at
#     all. The API exposes no upload, and adding one is a separate decision that
#     should be argued on its own.
#   * `s3:DeleteObjectVersion` is deliberately absent. If the bucket is ever
#     versioned, deletes become recoverable tombstones rather than erasures, and
#     this role cannot reach past them. Worth actually turning versioning on,
#     now that the prefix is not doing any confining.
#
# `GetObject` is what signs presigned URLs and what HeadObject checks against;
# both read the same permission. `CopyObject` — which is what a rename, a move
# and a favourite all are — needs `GetObject` on the source and `PutObject` on
# the destination. Favourites need no grant of their own for that reason: the
# source and the destination are both inside the same root everything else here
# is scoped to.
data "aws_iam_policy_document" "media_access" {
  statement {
    sid       = "ListBrowsableRoot"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.media_bucket_name}"]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      # A listing of the root arrives with `s3:prefix` absent or empty, so the
      # bare root is listed alongside the wildcard. `distinct` because an empty
      # root collapses two of the three into the same value.
      values = distinct(["${var.media_root_prefix}*", var.media_root_prefix, ""])
    }
  }

  statement {
    sid       = "ReadMediaObjects"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${var.media_bucket_name}/${var.media_root_prefix}*"]
  }

  statement {
    sid       = "ManageMediaObjects"
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::${var.media_bucket_name}/${var.media_root_prefix}*"]
  }
}

# Renamed from `media_read`, which is no longer what it grants. An inline role
# policy carries no data, so replacing it costs nothing.
resource "aws_iam_role_policy" "media_access" {
  name   = "${local.api_name}-media-access"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.media_access.json
}

# ---------------------------------------------------------------------------
# Lambda — the deploy workflow owns image_uri + environment after creation
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "api" {
  function_name = local.api_name
  role          = aws_iam_role.api.arn
  package_type  = "Image"
  image_uri     = local.api_image
  # 15s was ample while every request was one listing. A folder rename is a
  # CopyObject per key — server-side, so the bytes never move through here, but
  # still one round trip each — and `STUDIO_MAX_FOLDER_OBJECTS` bounds that at
  # 2000. The Lambda refuses anything larger rather than relying on this number,
  # so the timeout is the backstop and the config value is the contract.
  timeout     = 60
  memory_size = 512

  environment {
    variables = {
      STUDIO_MEDIA_BUCKET      = var.media_bucket_name
      STUDIO_MEDIA_ROOT_PREFIX = var.media_root_prefix
      STUDIO_ALLOWED_ORIGIN    = var.allowed_origin
    }
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [image_uri, environment]
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.api_name}"
  retention_in_days = 14
  tags              = var.tags
}
