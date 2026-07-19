output "bucket_id" {
  description = "Frontend S3 bucket ID"
  value       = aws_s3_bucket.frontend.id
}

output "bucket_arn" {
  description = "Frontend S3 bucket ARN"
  value       = aws_s3_bucket.frontend.arn
}

output "bucket_regional_domain_name" {
  description = "Frontend S3 bucket regional domain name"
  value       = aws_s3_bucket.frontend.bucket_regional_domain_name
}

output "dynamodb_table_arns" {
  description = "DynamoDB table ARNs used by the Humbugg backend"
  value = {
    profiles         = aws_dynamodb_table.profiles.arn
    groups           = aws_dynamodb_table.groups.arn
    groupmembers     = aws_dynamodb_table.groupmembers.arn
    draws            = aws_dynamodb_table.draws.arn
    audit_events     = aws_dynamodb_table.audit_events.arn
    analytics_events = aws_dynamodb_table.analytics_events.arn
  }
}

output "email_messages_table_arn" {
  description = "DynamoDB table ARN used for transactional email idempotency"
  value       = aws_dynamodb_table.email_messages.arn
}
