output "core_table_name" {
  description = "Name of the scout-core table"
  value       = aws_dynamodb_table.core.name
}

output "core_table_arn" {
  description = "ARN of the scout-core table"
  value       = aws_dynamodb_table.core.arn
}

output "settings_table_name" {
  description = "Name of the scout-settings table"
  value       = aws_dynamodb_table.settings.name
}

output "settings_table_arn" {
  description = "ARN of the scout-settings table"
  value       = aws_dynamodb_table.settings.arn
}
