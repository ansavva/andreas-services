output "intake_table_name" {
  description = "Name of the intake DynamoDB table"
  value       = aws_dynamodb_table.intake.name
}

output "intake_table_arn" {
  description = "ARN of the intake DynamoDB table"
  value       = aws_dynamodb_table.intake.arn
}
