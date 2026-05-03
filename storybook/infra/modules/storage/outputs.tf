# modules/storage/outputs.tf

output "backend_files_bucket_id" {
  description = "Backend files S3 bucket ID"
  value       = aws_s3_bucket.backend_files.id
}

output "backend_files_bucket_arn" {
  description = "Backend files S3 bucket ARN"
  value       = aws_s3_bucket.backend_files.arn
}

output "frontend_bucket_id" {
  description = "Frontend S3 bucket ID (if created)"
  value       = var.create_frontend_bucket ? aws_s3_bucket.frontend[0].id : null
}

output "frontend_bucket_arn" {
  description = "Frontend S3 bucket ARN (if created)"
  value       = var.create_frontend_bucket ? aws_s3_bucket.frontend[0].arn : null
}

output "frontend_bucket_regional_domain_name" {
  description = "Frontend S3 bucket regional domain name (if created)"
  value       = var.create_frontend_bucket ? aws_s3_bucket.frontend[0].bucket_regional_domain_name : null
}
