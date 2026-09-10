# Production alerting.
#
# One SNS topic per service, email subscriptions (decision 2026-09-09). Every alarm
# here sets both `alarm_actions` and `ok_actions`, so a recovery mail closes the loop
# and silence means healthy rather than unmonitored. `treat_missing_data =
# "notBreaching"` throughout: these metrics are only published when something happens,
# so absence is the healthy state, not INSUFFICIENT_DATA.

locals {
  name = "${var.project}-${var.environment}"

  topic_actions = [aws_sns_topic.alerts.arn]

  throttled_lambdas = {
    for key, fn in var.lambda_functions : key => fn.function_name if fn.throttle_alarm
  }
}

resource "aws_sns_topic" "alerts" {
  name = "${local.name}-alerts"

  tags = var.tags
}

# An email subscription lands in PendingConfirmation and delivers nothing until the
# recipient clicks the AWS link. Terraform cannot confirm it and will keep reporting
# the subscription as created — see the README.
resource "aws_sns_topic_subscription" "email" {
  count = var.alert_email != "" ? 1 : 0

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Lambda errors. The API threshold is 3 rather than 1 deliberately: a container
# Lambda cold-starting on a fresh image, or a single request losing a race with a
# DynamoDB retry, produces a lone error that resolves itself. Three failures inside
# one 5-minute window is a fault, not noise. The email-status consumer keeps a
# threshold of 1 — every error there is a delivery status that never reached the
# ledger, and it processes far too little traffic for one to be noise.
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = var.lambda_functions

  alarm_name          = "${local.name}-${each.key}-errors"
  alarm_description   = "${each.value.function_name} raised ${each.value.error_threshold} or more errors in 5 minutes"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = each.value.error_threshold
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = each.value.function_name
  }

  alarm_actions = local.topic_actions
  ok_actions    = local.topic_actions

  tags = var.tags
}

# Throttles have no benign case — the function was asked to run and could not, so
# the request was dropped. Threshold 1.
resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  for_each = local.throttled_lambdas

  alarm_name          = "${local.name}-${each.key}-throttles"
  alarm_description   = "${each.value} was throttled — concurrency exhausted, requests dropped"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = each.value
  }

  alarm_actions = local.topic_actions
  ok_actions    = local.topic_actions

  tags = var.tags
}

# HTTP APIs publish `5xx`, not `5XXError` — that name belongs to REST APIs. Confirmed
# against `aws cloudwatch list-metrics --namespace AWS/ApiGateway` for both api ids.
# The gateway counts its own faults here too (integration timeout, authorizer failure),
# so this catches failures the Lambda error metric never sees.
resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  for_each = var.api_ids

  alarm_name          = "${local.name}-${each.key}-5xx"
  alarm_description   = "HTTP API ${each.value} returned ${var.api_5xx_threshold} or more 5xx responses in 5 minutes"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "5xx"
  namespace           = "AWS/ApiGateway"
  period              = 300
  statistic           = "Sum"
  threshold           = var.api_5xx_threshold
  treat_missing_data  = "notBreaching"

  dimensions = {
    ApiId = each.value
  }

  alarm_actions = local.topic_actions
  ok_actions    = local.topic_actions

  tags = var.tags
}

# Every table is on-demand, which caps sustained throughput per partition rather than
# per table: a hot partition still throttles, and the request fails. Threshold 1.
resource "aws_cloudwatch_metric_alarm" "dynamodb_read_throttles" {
  for_each = var.dynamodb_table_names

  alarm_name          = "${each.value}-read-throttles"
  alarm_description   = "${each.value} throttled a read — likely partition heat"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ReadThrottleEvents"
  namespace           = "AWS/DynamoDB"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    TableName = each.value
  }

  alarm_actions = local.topic_actions
  ok_actions    = local.topic_actions

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "dynamodb_write_throttles" {
  for_each = var.dynamodb_table_names

  alarm_name          = "${each.value}-write-throttles"
  alarm_description   = "${each.value} throttled a write — likely partition heat"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "WriteThrottleEvents"
  namespace           = "AWS/DynamoDB"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    TableName = each.value
  }

  alarm_actions = local.topic_actions
  ok_actions    = local.topic_actions

  tags = var.tags
}
