# modules/image_queue/outputs.tf

output "queue_url" {
  description = "Main SQS queue URL"
  value       = aws_sqs_queue.main.url
}

output "queue_arn" {
  description = "Main SQS queue ARN"
  value       = aws_sqs_queue.main.arn
}

output "dlq_url" {
  description = "Dead-letter queue URL"
  value       = aws_sqs_queue.dlq.url
}

output "dlq_arn" {
  description = "Dead-letter queue ARN"
  value       = aws_sqs_queue.dlq.arn
}
