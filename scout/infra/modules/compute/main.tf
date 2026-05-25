locals {
  name_suffix          = var.pr_number != "" ? "-pr-${var.pr_number}" : ""
  email_processor_name = "scout-email-processor${local.name_suffix}"
  events_api_name      = "scout-events-api${local.name_suffix}"
  processor_name       = "scout-source-run-processor${local.name_suffix}"
  scheduler_name       = "scout-scheduler${local.name_suffix}"
  sweep_name           = "scout-sweep${local.name_suffix}"

  # The source-run processor, scheduler and sweep share the events-api image and
  # only override the container command, so the image is built once.
  events_api_image = var.create_ecr ? "${aws_ecr_repository.events_api[0].repository_url}:latest" : var.events_api_image_uri
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

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
          "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/scout-*",
          "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/scout-*/index/*",
        ]
      },
      {
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:scout-email-processor*",
          "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:scout-source-run-processor*",
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
        ]
        Resource = [
          "arn:aws:s3:::scout-artifacts-*",
          "arn:aws:s3:::scout-artifacts-*/*",
          "arn:aws:s3:::scout-images-*",
          "arn:aws:s3:::scout-images-*/*",
        ]
      },
    ]
  })
}

resource "aws_lambda_function" "email_processor" {
  function_name = local.email_processor_name
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = var.create_ecr ? "${aws_ecr_repository.email_processor[0].repository_url}:latest" : var.email_processor_image_uri
  timeout       = 300
  memory_size   = 256

  environment {
    variables = merge(var.email_processor_env_vars, {
      SCOUT_TABLE_SUFFIX = var.table_suffix
    })
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
  image_uri     = var.create_ecr ? "${aws_ecr_repository.events_api[0].repository_url}:latest" : var.events_api_image_uri
  timeout       = 30
  memory_size   = 128

  environment {
    variables = {
      SCOUT_TABLE_SUFFIX = var.table_suffix
      SCOUT_PROCESSOR_FN = local.processor_name
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

# --- Source-run processor (runs fetch + Agent SDK extraction for one source) --
resource "aws_lambda_function" "source_run_processor" {
  function_name = local.processor_name
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = local.events_api_image
  timeout       = 300
  memory_size   = 512

  image_config {
    command = ["processor_handler.lambda_handler"]
  }

  environment {
    variables = merge(var.processor_env_vars, {
      SCOUT_TABLE_SUFFIX     = var.table_suffix
      SCOUT_ARTIFACTS_BUCKET = var.artifacts_bucket
      SCOUT_IMAGES_BUCKET    = var.images_bucket
    })
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [image_uri, environment]
  }
}

resource "aws_cloudwatch_log_group" "source_run_processor" {
  name              = "/aws/lambda/${aws_lambda_function.source_run_processor.function_name}"
  retention_in_days = 14

  tags = var.tags
}

# --- Scheduler (dispatches due sources to the processor) ----------------------
resource "aws_lambda_function" "scheduler" {
  function_name = local.scheduler_name
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = local.events_api_image
  timeout       = 60
  memory_size   = 256

  image_config {
    command = ["scheduler_handler.lambda_handler"]
  }

  environment {
    variables = {
      SCOUT_TABLE_SUFFIX = var.table_suffix
      SCOUT_PROCESSOR_FN = local.processor_name
    }
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [image_uri, environment]
  }
}

resource "aws_cloudwatch_log_group" "scheduler" {
  name              = "/aws/lambda/${aws_lambda_function.scheduler.function_name}"
  retention_in_days = 14

  tags = var.tags
}

# --- Sweep (orphaned-run recovery + past-flag materialization) ----------------
resource "aws_lambda_function" "sweep" {
  function_name = local.sweep_name
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = local.events_api_image
  timeout       = 120
  memory_size   = 256

  image_config {
    command = ["sweep_handler.lambda_handler"]
  }

  environment {
    variables = {
      SCOUT_TABLE_SUFFIX = var.table_suffix
    }
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [image_uri, environment]
  }
}

resource "aws_cloudwatch_log_group" "sweep" {
  name              = "/aws/lambda/${aws_lambda_function.sweep.function_name}"
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

# Scheduler tick — dispatches sources whose next_run_at is due.
resource "aws_cloudwatch_event_rule" "scheduler" {
  count               = var.create_eventbridge ? 1 : 0
  name                = "scout-scheduler-tick"
  description         = "Dispatch due source runs"
  schedule_expression = "rate(15 minutes)"

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "scheduler" {
  count     = var.create_eventbridge ? 1 : 0
  rule      = aws_cloudwatch_event_rule.scheduler[0].name
  target_id = "ScoutScheduler"
  arn       = aws_lambda_function.scheduler.arn
}

resource "aws_lambda_permission" "scheduler" {
  count         = var.create_eventbridge ? 1 : 0
  statement_id  = "AllowEventBridgeInvokeScheduler"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.scheduler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.scheduler[0].arn
}

# Sweep tick — reconciles orphaned runs and refreshes past flags.
resource "aws_cloudwatch_event_rule" "sweep" {
  count               = var.create_eventbridge ? 1 : 0
  name                = "scout-sweep-tick"
  description         = "Reconcile orphaned runs and materialize past status"
  schedule_expression = "rate(1 hour)"

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "sweep" {
  count     = var.create_eventbridge ? 1 : 0
  rule      = aws_cloudwatch_event_rule.sweep[0].name
  target_id = "ScoutSweep"
  arn       = aws_lambda_function.sweep.arn
}

resource "aws_lambda_permission" "sweep" {
  count         = var.create_eventbridge ? 1 : 0
  statement_id  = "AllowEventBridgeInvokeSweep"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sweep.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.sweep[0].arn
}
