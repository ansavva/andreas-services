locals {
  name_prefix = "${var.project}-${var.environment}"

  events_api_name = "${local.name_prefix}-events-api"
  processor_name  = "${local.name_prefix}-source-run-processor"
  scheduler_name  = "${local.name_prefix}-scheduler"
  sweep_name      = "${local.name_prefix}-sweep"
  renderer_name   = "${local.name_prefix}-source-renderer"

  # The source-run processor, scheduler and sweep share the events-api image and
  # only override the container command, so the image is built once.
  events_api_image = var.create_ecr ? "${aws_ecr_repository.events_api[0].repository_url}:latest" : var.events_api_image_uri

  # The renderer (headless Chromium) is too heavy for the shared image, so it
  # ships from its own ECR repo.
  renderer_image = var.create_ecr ? "${aws_ecr_repository.renderer[0].repository_url}:latest" : var.renderer_image_uri
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_ecr_repository" "events_api" {
  count = var.create_ecr ? 1 : 0
  # NOT yet renamed to the convention, deliberately. Replacing an ECR repository
  # destroys the images it holds, and the Lambdas below reference
  # "<repo>:latest" — so a repo rename in this apply would create empty repos
  # and every Lambda creation would fail with no such image. The rename lands in
  # CI instead, where build-and-push populates the new repos before apply runs.
  # force_delete is already in state (see the earlier flags-only apply), so that
  # rename is unblocked whenever it happens.
  name                 = "scout-events-api"
  image_tag_mutability = "MUTABLE"

  # DeleteRepository refuses a repository that still holds images, which fails
  # the destroy half of a rename. The flag is read from prior state, so it has
  # to land in its own apply before the name changes (see CLAUDE.md).
  force_delete = true

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

resource "aws_ecr_repository" "renderer" {
  count = var.create_ecr ? 1 : 0
  # Deferred for the same reason as the events-api repository above.
  name                 = "scout-renderer"
  image_tag_mutability = "MUTABLE"

  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "renderer" {
  count      = var.create_ecr ? 1 : 0
  repository = aws_ecr_repository.renderer[0].name

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
  name = "${local.name_prefix}-lambda-role"

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
  name = "${local.name_prefix}-lambda-policy"
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
          "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/${local.name_prefix}-*",
          "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/${local.name_prefix}-*/index/*",
        ]
      },
      {
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:${local.processor_name}",
          "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:${local.renderer_name}",
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
          "arn:aws:s3:::${var.artifacts_bucket}",
          "arn:aws:s3:::${var.artifacts_bucket}/*",
          "arn:aws:s3:::${var.images_bucket}",
          "arn:aws:s3:::${var.images_bucket}/*",
        ]
      },
    ]
  })
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
      SCOUT_CORE_TABLE     = var.core_table_name
      SCOUT_SETTINGS_TABLE = var.settings_table_name
      SCOUT_PROCESSOR_FN   = local.processor_name
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
    command = ["scout_core.handlers.aws.jobs.processor_handler.lambda_handler"]
  }

  environment {
    variables = merge(var.processor_env_vars, {
      SCOUT_CORE_TABLE       = var.core_table_name
      SCOUT_SETTINGS_TABLE   = var.settings_table_name
      SCOUT_ARTIFACTS_BUCKET = var.artifacts_bucket
      SCOUT_IMAGES_BUCKET    = var.images_bucket
      SCOUT_RENDERER_FN      = local.renderer_name
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
    command = ["scout_core.handlers.aws.jobs.scheduler_handler.lambda_handler"]
  }

  environment {
    variables = {
      SCOUT_CORE_TABLE     = var.core_table_name
      SCOUT_SETTINGS_TABLE = var.settings_table_name
      SCOUT_PROCESSOR_FN   = local.processor_name
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
    command = ["scout_core.handlers.aws.jobs.sweep_handler.lambda_handler"]
  }

  environment {
    variables = {
      SCOUT_CORE_TABLE     = var.core_table_name
      SCOUT_SETTINGS_TABLE = var.settings_table_name
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

# --- Source renderer (patchright/Chrome headful via Xvfb; invoked sync) --------
resource "aws_lambda_function" "source_renderer" {
  function_name = local.renderer_name
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = local.renderer_image
  timeout       = 90
  memory_size   = 3008

  ephemeral_storage {
    size = 1024
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [image_uri, environment]
  }
}

resource "aws_cloudwatch_log_group" "source_renderer" {
  name              = "/aws/lambda/${aws_lambda_function.source_renderer.function_name}"
  retention_in_days = 14

  tags = var.tags
}

# Scheduler tick — dispatches sources whose next_run_at is due.
resource "aws_cloudwatch_event_rule" "scheduler" {
  count               = var.create_eventbridge ? 1 : 0
  name                = "${local.name_prefix}-scheduler-tick"
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
  name                = "${local.name_prefix}-sweep-tick"
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
