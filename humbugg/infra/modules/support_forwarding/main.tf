data "aws_caller_identity" "current" {}

locals {
  name_prefix        = "${var.project}-support-${var.environment}"
  inbound_bucket     = "${var.project}-support-inbound-${var.environment}"
  inbound_prefix     = "inbound/"
  rule_set_name      = "${var.project}-inbound-${var.environment}"
  rule_name          = "${var.project}-support-forward"
  forward_to_param   = "/${var.project}/prod/support-forward-to"
  smtp_inbound_host  = "inbound-smtp.${var.aws_region}.amazonaws.com"
  account_id         = data.aws_caller_identity.current.account_id
  receipt_rule_arn   = "arn:aws:ses:${var.aws_region}:${local.account_id}:receipt-rule-set/${local.rule_set_name}:receipt-rule/${local.rule_name}"
  own_domains        = var.domain_name
  allowed_recipients = var.support_recipient
}

# --------------------------------------------------------------------------- #
# Private destination secret (human-provided; never committed).
# The value is injected once via TF_VAR_support_forward_to and thereafter owned
# outside Terraform (rotated in the console / via CI), so we ignore drift.
# --------------------------------------------------------------------------- #
resource "aws_ssm_parameter" "forward_to" {
  name        = local.forward_to_param
  description = "Private destination for forwarded support@ mail (human secret)"
  type        = "SecureString"
  value       = var.support_forward_to != "" ? var.support_forward_to : "TODO-set-via-secret"

  lifecycle {
    ignore_changes = [value]
  }

  tags = var.tags
}

# --------------------------------------------------------------------------- #
# Inbound mail storage: SES writes the raw MIME here; the Lambda reads it.
# --------------------------------------------------------------------------- #
resource "aws_s3_bucket" "inbound" {
  bucket        = local.inbound_bucket
  force_destroy = false

  tags = var.tags
}

resource "aws_s3_bucket_public_access_block" "inbound" {
  bucket = aws_s3_bucket.inbound.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "inbound" {
  bucket = aws_s3_bucket.inbound.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "inbound" {
  bucket = aws_s3_bucket.inbound.id

  rule {
    id     = "expire-raw-inbound"
    status = "Enabled"

    filter {
      prefix = local.inbound_prefix
    }

    expiration {
      days = var.inbound_object_expiration_days
    }
  }
}

# Allow SES (this account only) to deposit raw messages.
resource "aws_s3_bucket_policy" "inbound" {
  bucket = aws_s3_bucket.inbound.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowSESInboundPuts"
      Effect    = "Allow"
      Principal = { Service = "ses.amazonaws.com" }
      Action    = "s3:PutObject"
      Resource  = "${aws_s3_bucket.inbound.arn}/*"
      Condition = {
        StringEquals = { "aws:SourceAccount" = local.account_id }
        StringLike   = { "aws:SourceArn" = "arn:aws:ses:${var.aws_region}:${local.account_id}:receipt-rule-set/${local.rule_set_name}:receipt-rule/*" }
      }
    }]
  })
}

# --------------------------------------------------------------------------- #
# Dead-letter queue for async Lambda failures (S3/SES transient errors).
# --------------------------------------------------------------------------- #
resource "aws_sqs_queue" "dlq" {
  name                      = "${local.name_prefix}-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = var.tags
}

# --------------------------------------------------------------------------- #
# Forwarder Lambda (Python 3.11, zip). stdlib email + boto3 only, so Terraform
# packages the source directly — no ECR/CI build step required.
# --------------------------------------------------------------------------- #
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = var.lambda_source_dir
  output_path = "${path.module}/.build/support_forwarder.zip"
}

resource "aws_iam_role" "lambda" {
  name = "${local.name_prefix}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda" {
  name = "${local.name_prefix}-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadRawInbound"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.inbound.arn}/${local.inbound_prefix}*"
      },
      {
        Sid      = "ReadForwardSecret"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = aws_ssm_parameter.forward_to.arn
      },
      {
        # Send only the forward, only from the verified sender identity.
        Sid      = "SendForward"
        Effect   = "Allow"
        Action   = ["ses:SendRawEmail"]
        Resource = var.ses_identity_arn
        Condition = {
          StringEquals = { "ses:FromAddress" = var.from_address }
        }
      },
      {
        Sid      = "DeadLetter"
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.dlq.arn
      },
    ]
  })
}

resource "aws_lambda_function" "forwarder" {
  function_name    = "${local.name_prefix}-forwarder"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.11"
  handler          = "support_forwarder.handler.lambda_handler"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  timeout          = 30
  memory_size      = 256

  dead_letter_config {
    target_arn = aws_sqs_queue.dlq.arn
  }

  environment {
    variables = {
      INBOUND_BUCKET           = aws_s3_bucket.inbound.id
      INBOUND_PREFIX           = local.inbound_prefix
      FROM_ADDRESS             = var.from_address
      SUPPORT_FORWARD_TO_PARAM = aws_ssm_parameter.forward_to.name
      ALLOWED_RECIPIENTS       = local.allowed_recipients
      OWN_DOMAINS              = local.own_domains
      MAX_MESSAGE_BYTES        = tostring(var.max_message_bytes)
      MAX_ATTACHMENT_BYTES     = tostring(var.max_attachment_bytes)
    }
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${aws_lambda_function.forwarder.function_name}"
  retention_in_days = 14

  tags = var.tags
}

# SES must be allowed to invoke the Lambda (from this account's rule set).
resource "aws_lambda_permission" "ses_invoke" {
  statement_id   = "AllowSESInvoke"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.forwarder.function_name
  principal      = "ses.amazonaws.com"
  source_account = local.account_id
  source_arn     = local.receipt_rule_arn
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${local.name_prefix}-forwarder-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.forwarder.function_name
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name          = "${local.name_prefix}-dlq-not-empty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.dlq.name
  }

  tags = var.tags
}

# --------------------------------------------------------------------------- #
# SES inbound: receipt rule set + rule matching only the support recipient.
# NOTE: only ONE receipt rule set can be active per account per region.
# --------------------------------------------------------------------------- #
resource "aws_ses_receipt_rule_set" "main" {
  rule_set_name = local.rule_set_name
}

resource "aws_ses_active_receipt_rule_set" "main" {
  rule_set_name = aws_ses_receipt_rule_set.main.rule_set_name
}

resource "aws_ses_receipt_rule" "support" {
  name          = local.rule_name
  rule_set_name = aws_ses_receipt_rule_set.main.rule_set_name
  recipients    = [var.support_recipient]
  enabled       = true
  scan_enabled  = true # populates spam/virus verdicts
  tls_policy    = "Optional"

  s3_action {
    position          = 1
    bucket_name       = aws_s3_bucket.inbound.id
    object_key_prefix = local.inbound_prefix
  }

  lambda_action {
    position        = 2
    function_arn    = aws_lambda_function.forwarder.arn
    invocation_type = "Event" # async → Lambda retries then DLQ on failure
  }

  depends_on = [
    aws_s3_bucket_policy.inbound,
    aws_lambda_permission.ses_invoke,
  ]
}

# --------------------------------------------------------------------------- #
# Route53: apex MX so mail for support@humbugg.com reaches SES inbound.
# --------------------------------------------------------------------------- #
resource "aws_route53_record" "inbound_mx" {
  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = "MX"
  ttl     = 300
  records = ["10 ${local.smtp_inbound_host}"]
}
