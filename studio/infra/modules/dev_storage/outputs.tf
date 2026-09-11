output "media_bucket_name" {
  description = "Name (id) of the development media bucket."
  value       = aws_s3_bucket.media.id
}

output "media_bucket_arn" {
  description = "ARN of the development media bucket."
  value       = aws_s3_bucket.media.arn
}

output "catalog_table_name" {
  description = "Name of the development catalog table; the local API reads it from its environment."
  value       = aws_dynamodb_table.catalog.name
}

output "catalog_table_arn" {
  description = "ARN of the development catalog table. Indexes are `<arn>/index/*`."
  value       = aws_dynamodb_table.catalog.arn
}
