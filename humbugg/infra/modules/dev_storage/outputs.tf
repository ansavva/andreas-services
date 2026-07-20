output "table_names" {
  description = "Development DynamoDB table names consumed by the local backend"
  value = {
    profiles         = aws_dynamodb_table.profiles.name
    groups           = aws_dynamodb_table.groups.name
    groupmembers     = aws_dynamodb_table.groupmembers.name
    draws            = aws_dynamodb_table.draws.name
    audit_events     = aws_dynamodb_table.audit_events.name
    analytics_events = aws_dynamodb_table.analytics_events.name
    email_messages   = aws_dynamodb_table.email_messages.name
    billing          = aws_dynamodb_table.billing.name
  }
}

output "app_bucket_name" {
  description = "Development application object bucket name"
  value       = aws_s3_bucket.app.id
}
