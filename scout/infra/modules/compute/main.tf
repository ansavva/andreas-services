locals {
  name_suffix          = var.pr_number != "" ? "-pr-${var.pr_number}" : ""
  email_processor_name = "scout-email-processor${local.name_suffix}"
  events_api_name      = "scout-events-api${local.name_suffix}"
}

resource "aws_ecr_repository" "email_processor" {
  count                = var.create_ecr ? 1 : 0
  name                 = "scout-email-processor"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "email_processor" {
  count      = var.create_ecr ? 1 : 0
  repository = aws_ecr_repository.email_processor[0].name

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

resource "aws_ecr_repository" "events_api" {
  count                = var.create_ecr ? 1 : 0
  name                 = "scout-events-api"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "events_api" {
  count      = var.create_ecr ? 1 : 0
  repository = aws_ecr_repository.events_api[0].name

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

resource "aws_iam_role" "lambda" {
  name = "scout-lambda-role${local.name_suffix}"

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

resource "aws_iam_role_policy" "lambda" {
  name = "scout-lambda-policy${local.name_suffix}"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
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
        Resource = [
          var.dynamodb_table_arn,
          "${var.dynamodb_table_arn}/index/*",
        ]
      },
    ]
  })
}

resource "aws_lambda_function" "email_processor" {
  function_name = local.email_processor_name
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = var.email_processor_image_uri
  timeout       = 300
  memory_size   = 256

  environment {
    variables = var.email_processor_env_vars
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [image_uri, environment]
  }
}

resource "aws_cloudwatch_log_group" "email_processor" {
  name              = "/aws/lambda/${aws_lambda_function.email_processor.function_name}"
  retention_in_days = 14

  tags = var.tags
}

resource "aws_lambda_function" "events_api" {
  function_name = local.events_api_name
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = var.events_api_image_uri
  timeout       = 30
  memory_size   = 128

  environment {
    variables = {
      EVENTS_TABLE_NAME = var.events_table_name
    }
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [image_uri, environment]
  }
}

resource "aws_cloudwatch_log_group" "events_api" {
  name              = "/aws/lambda/${aws_lambda_function.events_api.function_name}"
  retention_in_days = 14

  tags = var.tags
}

resource "aws_cloudwatch_event_rule" "weekly_processor" {
  count               = var.create_eventbridge ? 1 : 0
  name                = "scout-weekly-email-processor"
  description         = "Trigger email processor every Monday at 08:00 UTC"
  schedule_expression = "cron(0 8 ? * MON *)"

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "weekly_processor" {
  count     = var.create_eventbridge ? 1 : 0
  rule      = aws_cloudwatch_event_rule.weekly_processor[0].name
  target_id = "ScoutEmailProcessor"
  arn       = aws_lambda_function.email_processor.arn
}

resource "aws_lambda_permission" "eventbridge" {
  count         = var.create_eventbridge ? 1 : 0
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.email_processor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.weekly_processor[0].arn
}
