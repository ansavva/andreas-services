output "marketing_bucket_id" {
  description = "Frontend S3 bucket ID"
  value       = aws_s3_bucket.marketing.id
}

output "marketing_bucket_arn" {
  description = "Frontend S3 bucket ARN"
  value       = aws_s3_bucket.marketing.arn
}

output "marketing_bucket_regional_domain_name" {
  description = "Frontend S3 bucket regional domain name"
  value       = aws_s3_bucket.marketing.bucket_regional_domain_name
}

output "dynamodb_table_arns" {
  description = "DynamoDB table ARNs used by the Humbugg backend"
  value = {
    profiles         = aws_dynamodb_table.profiles.arn
    groups           = aws_dynamodb_table.groups.arn
    groupmembers     = aws_dynamodb_table.groupmembers.arn
    wishes           = aws_dynamodb_table.wishes.arn
    draws            = aws_dynamodb_table.draws.arn
    audit_events     = aws_dynamodb_table.audit_events.arn
    analytics_events = aws_dynamodb_table.analytics_events.arn
    billing          = aws_dynamodb_table.billing.arn
    invitations      = aws_dynamodb_table.invitations.arn
  }
}

output "email_messages_table_arn" {
  description = "DynamoDB table ARN used for transactional email idempotency"
  value       = aws_dynamodb_table.email_messages.arn
}

output "app_files_bucket_id" {
  description = "Application object S3 bucket name (holds avatars under the avatars/ prefix)"
  value       = aws_s3_bucket.app_files.id
}

output "app_files_bucket_arn" {
  description = "Application object S3 bucket ARN"
  value       = aws_s3_bucket.app_files.arn
}

output "app_files_bucket_regional_domain_name" {
  description = "Application object S3 bucket regional domain name (CloudFront origin)"
  value       = aws_s3_bucket.app_files.bucket_regional_domain_name
}

output "app_bucket_id" {
  description = "Expo web export S3 bucket ID"
  value       = aws_s3_bucket.app.id
}

output "app_bucket_arn" {
  description = "Expo web export S3 bucket ARN"
  value       = aws_s3_bucket.app.arn
}

output "app_bucket_regional_domain_name" {
  description = "Expo web export S3 bucket regional domain name"
  value       = aws_s3_bucket.app.bucket_regional_domain_name
}
