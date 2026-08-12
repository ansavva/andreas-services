data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "aws_iam_role" "humbugg" {
  name = var.humbugg_role_name
}

data "aws_acm_certificate" "wildcard" {
  domain      = "*.andreas.services"
  statuses    = ["ISSUED"]
  most_recent = true
}

locals {
  name                       = "${var.project}-${var.environment}"
  humbugg_product_config_set = "${local.name}-humbugg-product"
  humbugg_auth_config_set    = "${local.name}-humbugg-auth"
  humbugg_service = {
    sender_name             = "Humbugg"
    sender_address          = var.humbugg_sender_address
    allowed_categories      = ["invitation", "reminder", "draw_completed", "assignment_available", "account_exchange_event"]
    allowed_message_classes = ["exchange"]
    allowed_role_arns       = [data.aws_iam_role.humbugg.arn]
    configuration_set       = local.humbugg_product_config_set
    send_queue_url          = aws_sqs_queue.humbugg_send.url
    status_queue_url        = aws_sqs_queue.humbugg_status.url
    kill_switch_parameter   = aws_ssm_parameter.humbugg_exchange_email_enabled.name
  }
  service_registry_json = jsonencode({ humbugg = local.humbugg_service })
  configuration_set_registry_json = jsonencode({
    (local.humbugg_auth_config_set) = "humbugg"
  })
}

# ─── Container repository ────────────────────────────────────────────────────

resource "aws_ecr_repository" "mailer" {
  # No component segment: one image runs all three functions, so there is no
  # second repository for a component name to distinguish it from.
  name                 = local.name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "mailer" {
  repository = aws_ecr_repository.mailer.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the ten newest Mailer images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}

# ─── Private content storage ─────────────────────────────────────────────────

resource "aws_s3_bucket" "content" {
  # S3 names are globally unique, so this one carries the region suffix the
  # convention reserves for buckets.
  bucket        = "${local.name}-content-${data.aws_region.current.name}"
  force_destroy = false
  tags          = var.tags
}

resource "aws_s3_bucket_public_access_block" "content" {
  bucket                  = aws_s3_bucket.content.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "content" {
  bucket = aws_s3_bucket.content.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "content" {
  bucket = aws_s3_bucket.content.id

  cors_rule {
    allowed_methods = ["PUT"]
    allowed_origins = ["https://humbugg.com"]
    allowed_headers = [
      "content-type",
      "x-amz-checksum-sha256",
      "x-amz-meta-*",
    ]
    expose_headers  = ["etag"]
    max_age_seconds = 300
  }
}

resource "aws_s3_bucket_versioning" "content" {
  bucket = aws_s3_bucket.content.id
  versioning_configuration {
    status = "Disabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "content" {
  bucket = aws_s3_bucket.content.id

  rule {
    id     = "expire-mailer-content"
    status = "Enabled"
    filter {}
    expiration { days = 14 }
    abort_incomplete_multipart_upload { days_after_initiation = 1 }
  }
}

data "aws_iam_policy_document" "content_bucket" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.content.arn,
      "${aws_s3_bucket.content.arn}/*",
    ]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  statement {
    sid       = "SenderReadsOnlyCleanAttachments"
    effect    = "Deny"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.content.arn}/attachments/*"]
    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.sender.arn]
    }
    condition {
      test     = "StringNotEquals"
      variable = "s3:ExistingObjectTag/GuardDutyMalwareScanStatus"
      values   = ["NO_THREATS_FOUND"]
    }
  }
}

resource "aws_s3_bucket_policy" "content" {
  bucket = aws_s3_bucket.content.id
  policy = data.aws_iam_policy_document.content_bucket.json
}

# ─── DynamoDB ────────────────────────────────────────────────────────────────

resource "aws_dynamodb_table" "messages" {
  name         = "${local.name}-messages"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "record_key"

  attribute {
    name = "record_key"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery { enabled = true }
  server_side_encryption { enabled = true }
  tags = var.tags
}

resource "aws_dynamodb_table" "suppressions" {
  name         = "${local.name}-suppressions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "recipient_hash"

  attribute {
    name = "recipient_hash"
    type = "S"
  }

  point_in_time_recovery { enabled = true }
  server_side_encryption { enabled = true }
  tags = var.tags
}

# ─── Queues ──────────────────────────────────────────────────────────────────

resource "aws_sqs_queue" "humbugg_send_dlq" {
  name                      = "${local.name}-humbugg-send-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
  tags                      = var.tags
}

resource "aws_sqs_queue" "humbugg_send" {
  name                       = "${local.name}-humbugg-send"
  message_retention_seconds  = 86400
  visibility_timeout_seconds = 180
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.humbugg_send_dlq.arn
    maxReceiveCount     = 5
  })
  tags = var.tags
}

resource "aws_sqs_queue_redrive_allow_policy" "humbugg_send" {
  queue_url = aws_sqs_queue.humbugg_send_dlq.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.humbugg_send.arn]
  })
}

resource "aws_sqs_queue" "humbugg_status_dlq" {
  name                      = "${local.name}-humbugg-status-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
  tags                      = var.tags
}

resource "aws_sqs_queue" "humbugg_status" {
  name                       = "${local.name}-humbugg-status"
  message_retention_seconds  = 1209600
  visibility_timeout_seconds = 180
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.humbugg_status_dlq.arn
    maxReceiveCount     = 5
  })
  tags = var.tags
}

resource "aws_sqs_queue" "feedback_dlq" {
  name                      = "${local.name}-feedback-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
  tags                      = var.tags
}

resource "aws_sqs_queue" "feedback" {
  name                       = "${local.name}-feedback"
  message_retention_seconds  = 1209600
  visibility_timeout_seconds = 180
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.feedback_dlq.arn
    maxReceiveCount     = 5
  })
  tags = var.tags
}

# ─── SES feedback ────────────────────────────────────────────────────────────

resource "aws_sns_topic" "feedback" {
  name = "${local.name}-feedback"
  tags = var.tags
}

data "aws_iam_policy_document" "feedback_topic" {
  statement {
    sid       = "AllowSesPublish"
    effect    = "Allow"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.feedback.arn]
    principals {
      type        = "Service"
      identifiers = ["ses.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sns_topic_policy" "feedback" {
  arn    = aws_sns_topic.feedback.arn
  policy = data.aws_iam_policy_document.feedback_topic.json
}

data "aws_iam_policy_document" "feedback_queue" {
  statement {
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.feedback.arn]
    principals {
      type        = "Service"
      identifiers = ["sns.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_sns_topic.feedback.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "feedback" {
  queue_url = aws_sqs_queue.feedback.id
  policy    = data.aws_iam_policy_document.feedback_queue.json
}

resource "aws_sns_topic_subscription" "feedback" {
  topic_arn            = aws_sns_topic.feedback.arn
  protocol             = "sqs"
  endpoint             = aws_sqs_queue.feedback.arn
  raw_message_delivery = true
  depends_on           = [aws_sqs_queue_policy.feedback]
}

resource "aws_sesv2_configuration_set" "humbugg_product" {
  configuration_set_name = local.humbugg_product_config_set
  reputation_options { reputation_metrics_enabled = true }
  sending_options { sending_enabled = true }
  suppression_options { suppressed_reasons = ["BOUNCE", "COMPLAINT"] }
}

resource "aws_sesv2_configuration_set" "humbugg_auth" {
  configuration_set_name = local.humbugg_auth_config_set
  reputation_options { reputation_metrics_enabled = true }
  sending_options { sending_enabled = true }
  suppression_options { suppressed_reasons = ["BOUNCE", "COMPLAINT"] }
}

resource "aws_sesv2_configuration_set_event_destination" "humbugg_product" {
  configuration_set_name = aws_sesv2_configuration_set.humbugg_product.configuration_set_name
  event_destination_name = "${local.name}-feedback"
  event_destination {
    enabled = true
    matching_event_types = [
      "SEND", "DELIVERY", "DELIVERY_DELAY", "BOUNCE", "COMPLAINT", "REJECT",
    ]
    sns_destination { topic_arn = aws_sns_topic.feedback.arn }
  }
  depends_on = [aws_sns_topic_policy.feedback]
}

resource "aws_sesv2_configuration_set_event_destination" "humbugg_auth" {
  configuration_set_name = aws_sesv2_configuration_set.humbugg_auth.configuration_set_name
  event_destination_name = "${local.name}-feedback"
  event_destination {
    enabled = true
    matching_event_types = [
      "SEND", "DELIVERY", "DELIVERY_DELAY", "BOUNCE", "COMPLAINT", "REJECT",
    ]
    sns_destination { topic_arn = aws_sns_topic.feedback.arn }
  }
  depends_on = [aws_sns_topic_policy.feedback]
}

# ─── Lambda roles ────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ingress" {
  name               = "${local.name}-ingress-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
  tags               = var.tags
}

resource "aws_iam_role" "sender" {
  name               = "${local.name}-sender-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
  tags               = var.tags
}

resource "aws_iam_role" "feedback" {
  name               = "${local.name}-feedback-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "ingress_basic" {
  role       = aws_iam_role.ingress.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "sender_basic" {
  role       = aws_iam_role.sender.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "feedback_basic" {
  role       = aws_iam_role.feedback.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "ingress" {
  name = "${local.name}-ingress"
  role = aws_iam_role.ingress.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.messages.arn
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${aws_s3_bucket.content.arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.humbugg_send.arn
      },
    ]
  })
}

resource "aws_iam_role_policy" "sender" {
  name = "${local.name}-sender"
  role = aws_iam_role.sender.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
        Resource = [aws_dynamodb_table.messages.arn, aws_dynamodb_table.suppressions.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:GetObjectTagging", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.content.arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = aws_sqs_queue.humbugg_send.arn
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.humbugg_status.arn
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = aws_ssm_parameter.humbugg_exchange_email_enabled.arn
      },
      {
        Effect   = "Allow"
        Action   = ["ses:SendEmail"]
        Resource = "*"
        Condition = {
          StringEquals = { "ses:FromAddress" = var.humbugg_sender_address }
        }
      },
    ]
  })
}

resource "aws_iam_role_policy" "feedback" {
  name = "${local.name}-feedback"
  role = aws_iam_role.feedback.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = [aws_dynamodb_table.messages.arn, aws_dynamodb_table.suppressions.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = aws_sqs_queue.feedback.arn
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.humbugg_status.arn
      },
      {
        Effect   = "Allow"
        Action   = ["cloudwatch:PutMetricData"]
        Resource = "*"
        Condition = {
          StringEquals = { "cloudwatch:namespace" = "Mailer" }
        }
      },
    ]
  })
}

# ─── GuardDuty Malware Protection for S3 ─────────────────────────────────────

data "aws_iam_policy_document" "guardduty_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["malware-protection-plan.guardduty.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "guardduty" {
  name               = "${local.name}-guardduty-role"
  assume_role_policy = data.aws_iam_policy_document.guardduty_trust.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "guardduty" {
  name = "${local.name}-guardduty"
  role = aws_iam_role.guardduty.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetBucketLocation", "s3:GetBucketNotification", "s3:PutBucketNotification",
          "s3:GetBucketTagging", "s3:ListBucket",
        ]
        Resource = aws_s3_bucket.content.arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject", "s3:GetObjectVersion", "s3:GetObjectTagging", "s3:PutObjectTagging",
        ]
        Resource = "${aws_s3_bucket.content.arn}/attachments/*"
      },
      {
        Effect = "Allow"
        Action = [
          "events:PutRule", "events:DeleteRule", "events:PutTargets", "events:RemoveTargets",
        ]
        Resource = "arn:aws:events:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:rule/DO-NOT-DELETE-AmazonGuardDutyMalwareProtectionS3*"
      },
      {
        Effect   = "Allow"
        Action   = ["events:DescribeRule", "events:ListTargetsByRule"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["guardduty:SendSecurityTelemetry"]
        Resource = "*"
      },
    ]
  })
}

resource "aws_guardduty_malware_protection_plan" "attachments" {
  role = aws_iam_role.guardduty.arn

  protected_resource {
    s3_bucket {
      bucket_name     = aws_s3_bucket.content.id
      object_prefixes = ["attachments/"]
    }
  }

  actions {
    tagging { status = "ENABLED" }
  }

  tags       = var.tags
  depends_on = [aws_iam_role_policy.guardduty, aws_s3_bucket_policy.content]
}

locals {
  guardduty_alarm_statuses = {
    threat      = "THREATS_FOUND"
    unsupported = "UNSUPPORTED"
    denied      = "ACCESS_DENIED"
    failed      = "FAILED"
  }
}

resource "aws_cloudwatch_event_rule" "guardduty_result" {
  for_each = local.guardduty_alarm_statuses
  name     = "${local.name}-guardduty-${each.key}"
  event_pattern = jsonencode({
    source      = ["aws.guardduty"]
    detail-type = ["GuardDuty Malware Protection Object Scan Result"]
    detail = {
      s3ObjectDetails = {
        bucketName = [aws_s3_bucket.content.id]
      }
      scanResultDetails = {
        scanResultStatus = [each.value]
      }
    }
  })
  tags = var.tags
}

resource "aws_cloudwatch_event_target" "guardduty_result" {
  for_each = local.guardduty_alarm_statuses
  rule     = aws_cloudwatch_event_rule.guardduty_result[each.key].name
  arn      = aws_lambda_function.feedback.arn
  input    = jsonencode({ guardduty_status = each.value })
}

resource "aws_lambda_permission" "guardduty_events" {
  for_each      = local.guardduty_alarm_statuses
  statement_id  = "AllowGuardDutyEvent${title(each.key)}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.feedback.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.guardduty_result[each.key].arn
}

# ─── Lambda functions ────────────────────────────────────────────────────────

resource "aws_lambda_function" "ingress" {
  function_name = "${local.name}-ingress"
  role          = aws_iam_role.ingress.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.mailer.repository_url}:latest"
  timeout       = 30
  memory_size   = 512
  image_config { command = ["mailer.entrypoints.api_lambda.handler"] }
  environment {
    variables = {
      MAILER_CONTENT_BUCKET        = aws_s3_bucket.content.id
      MAILER_MESSAGES_TABLE        = aws_dynamodb_table.messages.name
      MAILER_SUPPRESSIONS_TABLE    = aws_dynamodb_table.suppressions.name
      MAILER_SERVICE_REGISTRY_JSON = local.service_registry_json
    }
  }
  lifecycle { ignore_changes = [image_uri, environment] }
  tags       = var.tags
  depends_on = [aws_iam_role_policy_attachment.ingress_basic, aws_iam_role_policy.ingress]
}

resource "aws_lambda_function" "sender" {
  function_name                  = "${local.name}-sender"
  role                           = aws_iam_role.sender.arn
  package_type                   = "Image"
  image_uri                      = "${aws_ecr_repository.mailer.repository_url}:latest"
  timeout                        = 120
  memory_size                    = 1024
  reserved_concurrent_executions = 5
  image_config { command = ["mailer.entrypoints.sender_lambda.handler"] }
  environment {
    variables = {
      MAILER_CONTENT_BUCKET        = aws_s3_bucket.content.id
      MAILER_MESSAGES_TABLE        = aws_dynamodb_table.messages.name
      MAILER_SUPPRESSIONS_TABLE    = aws_dynamodb_table.suppressions.name
      MAILER_SERVICE_REGISTRY_JSON = local.service_registry_json
    }
  }
  lifecycle { ignore_changes = [image_uri, environment] }
  tags       = var.tags
  depends_on = [aws_iam_role_policy_attachment.sender_basic, aws_iam_role_policy.sender]
}

resource "aws_lambda_function" "feedback" {
  function_name = "${local.name}-feedback"
  role          = aws_iam_role.feedback.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.mailer.repository_url}:latest"
  timeout       = 120
  memory_size   = 512
  image_config { command = ["mailer.entrypoints.feedback_lambda.handler"] }
  environment {
    variables = {
      MAILER_CONTENT_BUCKET                  = aws_s3_bucket.content.id
      MAILER_MESSAGES_TABLE                  = aws_dynamodb_table.messages.name
      MAILER_SUPPRESSIONS_TABLE              = aws_dynamodb_table.suppressions.name
      MAILER_SERVICE_REGISTRY_JSON           = local.service_registry_json
      MAILER_CONFIGURATION_SET_REGISTRY_JSON = local.configuration_set_registry_json
    }
  }
  lifecycle { ignore_changes = [image_uri, environment] }
  tags       = var.tags
  depends_on = [aws_iam_role_policy_attachment.feedback_basic, aws_iam_role_policy.feedback]
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each = {
    ingress  = aws_lambda_function.ingress.function_name
    sender   = aws_lambda_function.sender.function_name
    feedback = aws_lambda_function.feedback.function_name
  }
  name              = "/aws/lambda/${each.value}"
  retention_in_days = 14
  tags              = var.tags
}

resource "aws_lambda_event_source_mapping" "sender" {
  event_source_arn        = aws_sqs_queue.humbugg_send.arn
  function_name           = aws_lambda_function.sender.arn
  batch_size              = 5
  function_response_types = ["ReportBatchItemFailures"]
}

resource "aws_lambda_event_source_mapping" "feedback" {
  event_source_arn        = aws_sqs_queue.feedback.arn
  function_name           = aws_lambda_function.feedback.arn
  batch_size              = 10
  function_response_types = ["ReportBatchItemFailures"]
}

# ─── IAM-authenticated HTTP API ───────────────────────────────────────────────

resource "aws_apigatewayv2_api" "mailer" {
  name                         = local.name
  protocol_type                = "HTTP"
  disable_execute_api_endpoint = true
  tags                         = var.tags
}

resource "aws_apigatewayv2_integration" "ingress" {
  api_id                 = aws_apigatewayv2_api.mailer.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.ingress.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000
}

resource "aws_apigatewayv2_route" "messages" {
  api_id             = aws_apigatewayv2_api.mailer.id
  route_key          = "POST /v1/services/{service_id}/messages"
  authorization_type = "AWS_IAM"
  target             = "integrations/${aws_apigatewayv2_integration.ingress.id}"
}

resource "aws_apigatewayv2_route" "attachment_uploads" {
  api_id             = aws_apigatewayv2_api.mailer.id
  route_key          = "POST /v1/services/{service_id}/attachment-uploads"
  authorization_type = "AWS_IAM"
  target             = "integrations/${aws_apigatewayv2_integration.ingress.id}"
}

resource "aws_apigatewayv2_stage" "prod" {
  api_id      = aws_apigatewayv2_api.mailer.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = 40
    throttling_rate_limit  = 20
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      integrationMs  = "$context.integrationLatency"
    })
  }
  tags = var.tags
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/apigateway/${local.name}"
  retention_in_days = 14
  tags              = var.tags
}

resource "aws_lambda_permission" "api" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingress.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.mailer.execution_arn}/*/*"
}

resource "aws_apigatewayv2_domain_name" "mailer" {
  domain_name = var.domain_name
  domain_name_configuration {
    certificate_arn = data.aws_acm_certificate.wildcard.arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }
  tags = var.tags
}

resource "aws_apigatewayv2_api_mapping" "mailer" {
  api_id      = aws_apigatewayv2_api.mailer.id
  domain_name = aws_apigatewayv2_domain_name.mailer.id
  stage       = aws_apigatewayv2_stage.prod.id
}

resource "aws_route53_record" "mailer" {
  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = "A"
  alias {
    name                   = aws_apigatewayv2_domain_name.mailer.domain_name_configuration[0].target_domain_name
    zone_id                = aws_apigatewayv2_domain_name.mailer.domain_name_configuration[0].hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_iam_role_policy" "humbugg_invoke" {
  name = "invoke-${local.name}"
  role = data.aws_iam_role.humbugg.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = "execute-api:Invoke"
      Resource = [
        "${aws_apigatewayv2_api.mailer.execution_arn}/*/POST/v1/services/humbugg/messages",
        "${aws_apigatewayv2_api.mailer.execution_arn}/*/POST/v1/services/humbugg/attachment-uploads",
      ]
    }]
  })
}

# ─── Configuration and observability ─────────────────────────────────────────

resource "aws_ssm_parameter" "humbugg_exchange_email_enabled" {
  name  = "/mailer/prod/humbugg/exchange-email-enabled"
  type  = "String"
  value = "true"
  tags  = var.tags
}

resource "aws_ssm_parameter" "outputs" {
  for_each = {
    api-url                   = "https://${var.domain_name}"
    status-queue-arn          = aws_sqs_queue.humbugg_status.arn
    status-queue-url          = aws_sqs_queue.humbugg_status.url
    auth-configuration-set    = local.humbugg_auth_config_set
    product-configuration-set = local.humbugg_product_config_set
  }
  name  = "/mailer/prod/humbugg/${each.key}"
  type  = "String"
  value = each.value
  tags  = var.tags
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = {
    ingress  = aws_lambda_function.ingress.function_name
    sender   = aws_lambda_function.sender.function_name
    feedback = aws_lambda_function.feedback.function_name
  }
  alarm_name          = "${local.name}-${each.key}-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  dimensions          = { FunctionName = each.value }
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "dlq" {
  for_each = {
    send     = aws_sqs_queue.humbugg_send_dlq.name
    feedback = aws_sqs_queue.feedback_dlq.name
    status   = aws_sqs_queue.humbugg_status_dlq.name
  }
  alarm_name          = "${local.name}-${each.key}-dlq-not-empty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  dimensions          = { QueueName = each.value }
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "queue_age" {
  alarm_name          = "${local.name}-humbugg-send-oldest-message"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 900
  treat_missing_data  = "notBreaching"
  dimensions          = { QueueName = aws_sqs_queue.humbugg_send.name }
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "attachment_threat" {
  alarm_name          = "${local.name}-attachment-threat"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "AttachmentThreat"
  namespace           = "Mailer"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "attachment_scan_failure" {
  alarm_name          = "${local.name}-attachment-scan-failure"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "AttachmentScanFailure"
  namespace           = "Mailer"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "humbugg_rejects" {
  alarm_name          = "${local.name}-humbugg-rejects"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Reject"
  namespace           = "Mailer"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  dimensions          = { ServiceId = "humbugg" }
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "ses_bounce_rate" {
  alarm_name          = "${local.name}-ses-bounce-rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Reputation.BounceRate"
  namespace           = "AWS/SES"
  period              = 900
  statistic           = "Average"
  threshold           = 0.05
  treat_missing_data  = "notBreaching"
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "ses_complaint_rate" {
  alarm_name          = "${local.name}-ses-complaint-rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Reputation.ComplaintRate"
  namespace           = "AWS/SES"
  period              = 900
  statistic           = "Average"
  threshold           = 0.001
  treat_missing_data  = "notBreaching"
  tags                = var.tags
}
