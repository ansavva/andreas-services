# modules/image_queue/main.tf
# SQS queue + DLQ for image normalization jobs

locals {
  queue_name     = "${var.project}-image-normalization-${var.environment}"
  dlq_name       = "${local.queue_name}-dlq"
  max_receive    = 5
  visibility_sec = 900
}

resource "aws_sqs_queue" "dlq" {
  name                       = local.dlq_name
  visibility_timeout_seconds = local.visibility_sec
  message_retention_seconds  = 1209600
  max_message_size           = 262144
  delay_seconds              = 0
  receive_wait_time_seconds  = 0
  sqs_managed_sse_enabled    = true

  tags = var.tags
}

resource "aws_sqs_queue" "main" {
  name                       = local.queue_name
  visibility_timeout_seconds = local.visibility_sec
  message_retention_seconds  = 1209600
  max_message_size           = 262144
  delay_seconds              = 0
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = local.max_receive
  })

  tags = var.tags
}
