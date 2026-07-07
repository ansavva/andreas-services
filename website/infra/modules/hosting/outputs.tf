output "distribution_id" {
  description = "CloudFront distribution ID (for cache invalidation)"
  value       = aws_cloudfront_distribution.main.id
}

output "distribution_domain_name" {
  description = "CloudFront distribution domain name"
  value       = aws_cloudfront_distribution.main.domain_name
}

output "assets_bucket_name" {
  description = "S3 bucket holding hashed client assets"
  value       = aws_s3_bucket.assets.id
}
