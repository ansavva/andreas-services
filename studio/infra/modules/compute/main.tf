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

# READ-ONLY, AND THAT IS THE POINT.
#
# The media bucket belongs to the x-harness pipeline; this service is a viewer of
# it and nothing more. There is deliberately no PutObject, DeleteObject or
# AbortMultipartUpload here, so no bug, no compromised token and no future
# feature added in haste can write to or destroy that data — the role simply
# cannot. `ListBucket` is scoped by prefix so even listing cannot reach outside
# the browsable root.
#
# `GetObject` is what signs presigned URLs and what HeadObject checks against;
# both read the same permission.
data "aws_iam_policy_document" "media_read" {
  statement {
    sid       = "ListBrowsableRoot"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.media_bucket_name}"]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${var.media_root_prefix}*", var.media_root_prefix, ""]
    }
  }

  statement {
    sid       = "ReadMediaObjects"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${var.media_bucket_name}/${var.media_root_prefix}*"]
  }
}

resource "aws_iam_role_policy" "media_read" {
  name   = "${local.api_name}-media-read"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.media_read.json
}

# ---------------------------------------------------------------------------
# Lambda — the deploy workflow owns image_uri + environment after creation
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "api" {
  function_name = local.api_name
  role          = aws_iam_role.api.arn
  package_type  = "Image"
  image_uri     = local.api_image
  timeout       = 15
  memory_size   = 512

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
