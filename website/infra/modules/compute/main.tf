locals {
  prefix   = "${var.project}-${var.environment}"
  api_name = "${local.prefix}-api"
  www_name = "${local.prefix}-www"

  api_image = var.create_ecr ? "${aws_ecr_repository.api[0].repository_url}:latest" : var.api_image_uri
  www_image = var.create_ecr ? "${aws_ecr_repository.www[0].repository_url}:latest" : var.www_image_uri
}

data "aws_region" "current" {}

# ---------------------------------------------------------------------------
# ECR — one repo per image (Python API, SSR www)
# ---------------------------------------------------------------------------
# A repository name is immutable, so renaming one is a destroy and recreate, and
# DeleteRepository refuses a repository that still holds images. These hold
# nothing but CI build output that the next push rebuilds from git, so there is
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

resource "aws_ecr_repository" "www" {
  count                = var.create_ecr ? 1 : 0
  name                 = local.www_name
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

resource "aws_ecr_lifecycle_policy" "www" {
  count      = var.create_ecr ? 1 : 0
  repository = aws_ecr_repository.www[0].name
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
# IAM — backend role (DynamoDB + logs); www role (logs only)
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

resource "aws_iam_role_policy" "api" {
  name = "${local.api_name}-dynamodb"
  role = aws_iam_role.api.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:Query", "dynamodb:GetItem"]
        Resource = [var.intake_table_arn, "${var.intake_table_arn}/index/*"]
      },
    ]
  })
}

resource "aws_iam_role" "www" {
  name               = "${local.www_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "www" {
  name = "${local.www_name}-logs"
  role = aws_iam_role.www.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "arn:aws:logs:*:*:*"
    }]
  })
}

# ---------------------------------------------------------------------------
# Lambdas — the deploy workflow owns image_uri + environment after creation
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "api" {
  function_name = local.api_name
  role          = aws_iam_role.api.arn
  package_type  = "Image"
  image_uri     = local.api_image
  timeout       = 15
  memory_size   = 256

  environment {
    variables = {
      WEBSITE_INTAKE_TABLE = var.intake_table_name
    }
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [image_uri, environment]
  }
}

resource "aws_lambda_function" "www" {
  function_name = local.www_name
  role          = aws_iam_role.www.arn
  package_type  = "Image"
  image_uri     = local.www_image
  timeout       = 30
  memory_size   = 512

  environment {
    variables = {
      NODE_ENV = "production"
    }
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [image_uri, environment]
  }
}

# HTTP API fronting the SSR Lambda ($default proxy). Payload format 2.0 emits
# the same event shape the @react-router/architect handler consumes. CloudFront
# uses this API's endpoint as the SSR origin (like the other services front
# their Lambdas with API Gateway), which avoids the OAC-to-Function-URL path.
resource "aws_apigatewayv2_api" "www" {
  name          = local.www_name
  protocol_type = "HTTP"
  tags          = var.tags
}

resource "aws_apigatewayv2_integration" "www" {
  api_id                 = aws_apigatewayv2_api.www.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.www.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000
}

resource "aws_apigatewayv2_route" "www_default" {
  api_id    = aws_apigatewayv2_api.www.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.www.id}"
}

resource "aws_apigatewayv2_stage" "www" {
  api_id      = aws_apigatewayv2_api.www.id
  name        = "$default"
  auto_deploy = true
  tags        = var.tags
}

resource "aws_lambda_permission" "www_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.www.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.www.execution_arn}/*/*"
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.api_name}"
  retention_in_days = 14
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "www" {
  name              = "/aws/lambda/${local.www_name}"
  retention_in_days = 14
  tags              = var.tags
}
