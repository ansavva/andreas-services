output "bucket_id" {
  description = "Avatars S3 bucket name"
  value       = aws_s3_bucket.avatars.id
}

output "bucket_arn" {
  description = "Avatars S3 bucket ARN"
  value       = aws_s3_bucket.avatars.arn
}

output "bucket_regional_domain_name" {
  description = "Avatars S3 bucket regional domain name (CloudFront origin)"
  value       = aws_s3_bucket.avatars.bucket_regional_domain_name
}
