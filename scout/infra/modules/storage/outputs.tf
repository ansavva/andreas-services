output "bucket_id" {
  description = "S3 bucket name"
  value       = aws_s3_bucket.main.id
}

output "bucket_arn" {
  description = "S3 bucket ARN"
  value       = aws_s3_bucket.main.arn
}

output "website_endpoint" {
  description = "S3 website HTTP endpoint (without protocol)"
  value       = aws_s3_bucket_website_configuration.main.website_endpoint
}
