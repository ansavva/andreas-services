locals {
  name_prefix = "${var.project}-${var.environment}"
  api_name    = "${local.name_prefix}-api"
}

resource "aws_ecr_repository" "api" {
  count                = var.create_ecr ? 1 : 0
  name                 = local.api_name
  image_tag_mutability = "MUTABLE"

  # DeleteRepository refuses a repository that still holds images, which fails
  # the destroy half of a rename. The flag is read from prior state, so it has
  # to be here from creation (see root CLAUDE.md).
  force_delete = true

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
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_iam_role" "api" {
  name = "${local.api_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "api_logs" {
  name = "${local.api_name}-logs"
  role = aws_iam_role.api.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
      ]
      Resource = "arn:aws:logs:*:*:*"
    }]
  })
}

# Scoped to the one table this service owns and its indexes. No Scan: every
# access path is a keyed query, and granting Scan would let a bug read every
# teacher's pages in one call.
resource "aws_iam_role_policy" "api_dynamodb" {
  name = "${local.api_name}-dynamodb"
  role = aws_iam_role.api.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
      ]
      Resource = [
        var.pages_table_arn,
        "${var.pages_table_arn}/index/*",
      ]
    }]
  })
}

resource "aws_lambda_function" "api" {
  function_name = local.api_name
  role          = aws_iam_role.api.arn
  package_type  = "Image"
  image_uri     = var.create_ecr ? "${aws_ecr_repository.api[0].repository_url}:latest" : var.api_image_uri
  timeout       = 30
  memory_size   = 256

  environment {
    variables = {
      CLASSROOM_PAGES_TABLE     = var.pages_table_name
      CLASSROOM_PUBLIC_SITE_URL = var.public_site_url
    }
  }

  tags = var.tags

  # The deploy workflow owns both: `update-function-code` for the image and
  # `update-function-configuration` for env vars. Terraform sets initial values
  # on first creation only.
  lifecycle {
    ignore_changes = [image_uri, environment]
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${aws_lambda_function.api.function_name}"
  retention_in_days = 14

  tags = var.tags
}
