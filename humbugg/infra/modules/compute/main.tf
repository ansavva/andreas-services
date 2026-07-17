resource "aws_ecr_repository" "backend" {
  name                 = "${var.project}-backend-${var.environment}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}

resource "aws_ecr_repository" "frontend" {
  name                 = "${var.project}-frontend-${var.environment}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "frontend" {
  repository = aws_ecr_repository.frontend.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}

resource "aws_iam_role" "lambda" {
  name = "${var.project}-lambda-role-${var.environment}"

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

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role" "frontend" {
  name = "${var.project}-frontend-lambda-role-${var.environment}"

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

resource "aws_iam_role_policy_attachment" "frontend_basic" {
  role       = aws_iam_role.frontend.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_dynamodb" {
  name = "${var.project}-lambda-dynamodb-policy"
  role = aws_iam_role.lambda.id

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
        "dynamodb:Scan",
        "dynamodb:BatchWriteItem",
        "dynamodb:BatchGetItem",
      ]
      Resource = concat(
        values(var.dynamodb_table_arns),
        [for arn in values(var.dynamodb_table_arns) : "${arn}/index/*"]
      )
    }]
  })
}

resource "aws_iam_role_policy" "lambda_email_messages" {
  name = "${var.project}-lambda-email-messages-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:UpdateItem"]
      Resource = var.email_messages_table_arn
    }]
  })
}

resource "aws_iam_role" "email_status" {
  name = "${var.project}-email-status-role-${var.environment}"

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

resource "aws_iam_role_policy_attachment" "email_status_basic" {
  role       = aws_iam_role.email_status.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "email_status_queue" {
  name = "${var.project}-email-status-queue-${var.environment}"
  role = aws_iam_role.email_status.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "sqs:ChangeMessageVisibility",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
        "sqs:ReceiveMessage",
      ]
      Resource = var.mailer_status_queue_arn
    }]
  })
}

resource "aws_iam_role_policy" "email_status_table" {
  name = "${var.project}-email-status-table-${var.environment}"
  role = aws_iam_role.email_status.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:UpdateItem"]
      Resource = var.email_messages_table_arn
    }]
  })
}

resource "aws_lambda_function" "backend" {
  function_name = "${var.project}-backend-${var.environment}"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.backend.repository_url}:latest"
  timeout       = 30
  memory_size   = 512

  tags = var.tags

  lifecycle {
    ignore_changes = [
      image_uri,
      environment,
    ]
  }
}

resource "aws_lambda_function" "email_status" {
  function_name = "${var.project}-email-status-${var.environment}"
  role          = aws_iam_role.email_status.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.backend.repository_url}:latest"
  timeout       = 30
  memory_size   = 256

  environment {
    variables = {
      HUMBUGG_FUNCTION             = "email-status"
      HUMBUGG_EMAIL_MESSAGES_TABLE = "${var.project}-email-messages"
    }
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [
      image_uri,
      environment,
    ]
  }
}

resource "aws_lambda_event_source_mapping" "email_status" {
  event_source_arn                   = var.mailer_status_queue_arn
  function_name                      = aws_lambda_function.email_status.arn
  batch_size                         = 10
  maximum_batching_window_in_seconds = 1
  function_response_types            = ["ReportBatchItemFailures"]

  depends_on = [
    aws_iam_role_policy.email_status_queue,
    aws_iam_role_policy_attachment.email_status_basic,
  ]
}

resource "aws_lambda_function" "frontend" {
  function_name = "${var.project}-frontend-${var.environment}"
  role          = aws_iam_role.frontend.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.frontend.repository_url}:latest"
  timeout       = 30
  memory_size   = 512

  environment {
    variables = {
      NODE_ENV = "production"
    }
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [
      image_uri,
      environment,
    ]
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${aws_lambda_function.backend.function_name}"
  retention_in_days = 14

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "frontend" {
  name              = "/aws/lambda/${aws_lambda_function.frontend.function_name}"
  retention_in_days = 14

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "email_status" {
  name              = "/aws/lambda/${aws_lambda_function.email_status.function_name}"
  retention_in_days = 14

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "email_status_errors" {
  alarm_name          = "${var.project}-email-status-errors-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.email_status.function_name
  }

  tags = var.tags
}

resource "aws_apigatewayv2_api" "backend" {
  name          = "${var.project}-backend-${var.environment}"
  protocol_type = "HTTP"
  description   = "${var.project} Backend API"

  tags = var.tags
}

resource "aws_apigatewayv2_integration" "backend" {
  api_id           = aws_apigatewayv2_api.backend.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.backend.invoke_arn

  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "backend" {
  api_id    = aws_apigatewayv2_api.backend.id
  route_key = "ANY /api/{proxy+}"

  target             = "integrations/${aws_apigatewayv2_integration.backend.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "health" {
  api_id    = aws_apigatewayv2_api.backend.id
  route_key = "GET /health"
  target    = "integrations/${aws_apigatewayv2_integration.backend.id}"
}

resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.backend.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "${var.project}-cognito-${var.environment}"

  jwt_configuration {
    audience = [var.cognito_client_id]
    issuer   = "https://cognito-idp.us-east-1.amazonaws.com/${var.cognito_user_pool_id}"
  }
}

resource "aws_apigatewayv2_stage" "backend" {
  api_id      = aws_apigatewayv2_api.backend.id
  name        = "$default"
  auto_deploy = true

  tags = var.tags
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.backend.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.backend.execution_arn}/*/*"
}

resource "aws_apigatewayv2_api" "frontend" {
  name          = "${var.project}-frontend-${var.environment}"
  protocol_type = "HTTP"
  description   = "${var.project} SSR frontend"

  tags = var.tags
}

resource "aws_apigatewayv2_integration" "frontend" {
  api_id                 = aws_apigatewayv2_api.frontend.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.frontend.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000
}

resource "aws_apigatewayv2_route" "frontend" {
  api_id    = aws_apigatewayv2_api.frontend.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.frontend.id}"
}

resource "aws_apigatewayv2_stage" "frontend" {
  api_id      = aws_apigatewayv2_api.frontend.id
  name        = "$default"
  auto_deploy = true

  tags = var.tags
}

resource "aws_lambda_permission" "frontend_api_gateway" {
  statement_id  = "AllowAPIGatewayInvokeFrontend"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.frontend.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.frontend.execution_arn}/*/*"
}
