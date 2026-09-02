output "pages_table_name" {
  description = "Name of the classroom pages table"
  value       = aws_dynamodb_table.pages.name
}

output "pages_table_arn" {
  description = "ARN of the classroom pages table"
  value       = aws_dynamodb_table.pages.arn
}
