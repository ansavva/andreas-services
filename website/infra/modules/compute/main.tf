locals {
  name_suffix   = var.pr_number != "" ? "-pr-${var.pr_number}" : ""
  api_name      = "website-api${local.name_suffix}"
  frontend_name = "website-frontend${local.name_suffix}"

  api_image      = var.create_ecr ? "${aws_ecr_repository.api[0].repository_url}:latest" : var.api_image_uri
  frontend_image = var.create_ecr ? "${aws_ecr_repository.frontend[0].repository_url}:latest" : var.frontend_image_uri
}

data "aws_region" "current" {}

# ---------------------------------------------------------------------------
# ECR — one repo per image (Python API, SSR frontend)
# ---------------------------------------------------------------------------
resource "aws_ecr_repository" "api" {
  count                = var.create_ecr ? 1 : 0
  name                 = "website-api"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = var.tags
}

resource "aws_ecr_repository" "frontend" {
  count                = var.create_ecr ? 1 : 0
  name                 = "website-frontend"
  image_tag_mutability = "MUTABLE"
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

resource "aws_ecr_lifecycle_policy" "frontend" {
  count      = var.create_ecr ? 1 : 0
  repository = aws_ecr_repository.frontend[0].name
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
# IAM — backend role (DynamoDB + logs); frontend role (logs only)
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
  name               = "website-api-role${local.name_suffix}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "api" {
  name = "website-api-policy${local.name_suffix}"
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

resource "aws_iam_role" "frontend" {
  name               = "website-frontend-role${local.name_suffix}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "frontend" {
  name = "website-frontend-policy${local.name_suffix}"
  role = aws_iam_role.frontend.id
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
      WEBSITE_TABLE_SUFFIX = var.table_suffix
    }
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [image_uri, environment]
  }
}

resource "aws_lambda_function" "frontend" {
  function_name = local.frontend_name
  role          = aws_iam_role.frontend.arn
  package_type  = "Image"
  image_uri     = local.frontend_image
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
resource "aws_apigatewayv2_api" "frontend" {
  name          = local.frontend_name
  protocol_type = "HTTP"
  tags          = var.tags
}

resource "aws_apigatewayv2_integration" "frontend" {
  api_id                 = aws_apigatewayv2_api.frontend.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.frontend.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000
}

resource "aws_apigatewayv2_route" "frontend_default" {
  api_id    = aws_apigatewayv2_api.frontend.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.frontend.id}"
}

resource "aws_apigatewayv2_stage" "frontend" {
  api_id      = aws_apigatewayv2_api.frontend.id
  name        = "$default"
  auto_deploy = true
  tags        = var.tags
}

resource "aws_lambda_permission" "frontend_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.frontend.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.frontend.execution_arn}/*/*"
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.api_name}"
  retention_in_days = 14
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "frontend" {
  name              = "/aws/lambda/${local.frontend_name}"
  retention_in_days = 14
  tags              = var.tags
}
