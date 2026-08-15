output "app_bucket_id" {
  description = "S3 bucket the deploy workflow syncs the built SPA into"
  value       = aws_s3_bucket.app.id
}

output "distribution_id" {
  description = "CloudFront distribution ID, for post-deploy invalidation"
  value       = aws_cloudfront_distribution.app.id
}

output "app_url" {
  description = "Public URL of the app"
  value       = "https://${var.domain_name}"
}
