output "table_name" {
  description = "Name of the catalog table; the API reads it from its environment."
  value       = aws_dynamodb_table.catalog.name
}

output "table_arn" {
  description = <<-EOT
    ARN of the catalog table. Pass this into the API role's policy rather than
    reconstructing the ARN from the name — that is what orders the grant after
    the table it grants access to. Indexes are `<arn>/index/*`.
  EOT
  value       = aws_dynamodb_table.catalog.arn
}
