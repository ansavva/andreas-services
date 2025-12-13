# ECR Repository for Lambda container image
resource "aws_ecr_repository" "backend" {
  name                 = "storybook-backend-${var.environment}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name = "storybook-backend"
  }
}

# ECR Lifecycle Policy
resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus     = "any"
        countType     = "imageCountMoreThan"
        countNumber   = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}

# IAM role for Lambda
resource "aws_iam_role" "lambda" {
  name = "storybook-lambda-role-${var.environment}"

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
}

# IAM policy for Lambda
resource "aws_iam_role_policy" "lambda" {
  name = "storybook-lambda-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.backend_files.arn,
          "${aws_s3_bucket.backend_files.arn}/*"
        ]
      }
    ]
  })
}

# Lambda Function
resource "aws_lambda_function" "backend" {
  function_name = "storybook-backend-${var.environment}"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.backend.repository_url}:latest"
  timeout       = 30
  memory_size   = 512

  environment {
    variables = {
      FLASK_ENV                   = var.environment
      AWS_COGNITO_REGION          = var.aws_region
      AWS_COGNITO_USER_POOL_ID    = aws_cognito_user_pool.main.id
      AWS_COGNITO_APP_CLIENT_ID   = aws_cognito_user_pool_client.main.id
      S3_BUCKET_NAME              = aws_s3_bucket.backend_files.id
      REPLICATE_API_TOKEN         = var.replicate_api_token
      APP_URL                     = "https://${var.app_subdomain}${var.frontend_path}"
    }
  }

  tags = {
    Name = "storybook-backend"
  }

  # The image_uri will be updated by GitHub Actions
  lifecycle {
    ignore_changes = [image_uri]
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${aws_lambda_function.backend.function_name}"
  retention_in_days = 14

  tags = {
    Name = "storybook-lambda-logs"
  }
}

# Lambda Function URL
resource "aws_lambda_function_url" "backend" {
  function_name      = aws_lambda_function.backend.function_name
  authorization_type = "NONE"

  cors {
    allow_credentials = true
    allow_origins     = [
      "https://${var.app_subdomain}",
      "http://localhost:5173"
    ]
    allow_methods     = ["*"]
    allow_headers     = ["*"]
    expose_headers    = ["*"]
    max_age           = 3600
  }
}

# API Gateway v2 (HTTP API) for custom domain
resource "aws_apigatewayv2_api" "backend" {
  name          = "storybook-backend-${var.environment}"
  protocol_type = "HTTP"
  description   = "Storybook Backend API"

  cors_configuration {
    allow_credentials = true
    allow_origins = [
      "https://${var.app_subdomain}",
      "http://localhost:5173"
    ]
    allow_methods = ["*"]
    allow_headers = ["*"]
    expose_headers = ["*"]
    max_age = 3600
  }
}

# API Gateway Integration with Lambda
resource "aws_apigatewayv2_integration" "backend" {
  api_id           = aws_apigatewayv2_api.backend.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.backend.invoke_arn

  payload_format_version = "2.0"
}

# API Gateway Route
resource "aws_apigatewayv2_route" "backend" {
  api_id    = aws_apigatewayv2_api.backend.id
  route_key = "$default"

  target = "integrations/${aws_apigatewayv2_integration.backend.id}"
}

# API Gateway Stage
resource "aws_apigatewayv2_stage" "backend" {
  api_id      = aws_apigatewayv2_api.backend.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
    })
  }
}

# CloudWatch Log Group for API Gateway
resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/storybook-backend-${var.environment}"
  retention_in_days = 14

  tags = {
    Name = "storybook-api-gateway-logs"
  }
}

# Lambda permission for API Gateway
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.backend.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.backend.execution_arn}/*/*"
}

# Note: Backend is accessed via CloudFront at storybook.andreas.services/api
# No separate custom domain needed for API Gateway
