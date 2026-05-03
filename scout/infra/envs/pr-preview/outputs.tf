output "s3_bucket_id" {
  description = "Shared PR preview S3 bucket name"
  value       = module.storage.bucket_id
}

output "cloudfront_distribution_id" {
  description = "Shared PR preview CloudFront distribution ID"
  value       = module.hosting.cloudfront_distribution_id
}

output "api_domain_name" {
  description = "Shared PR API custom domain name"
  value       = module.api_domain.domain_name
}
