output "api_endpoint" {
  description = "Public API URL"
  value       = module.api_gateway.invoke_url
}

output "s3_bucket" {
  description = "Frontend S3 bucket name"
  value       = module.storage.bucket_id
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = module.hosting.cloudfront_distribution_id
}

output "email_processor_function_name" {
  description = "Email processor Lambda function name"
  value       = module.compute.email_processor_function_name
}

output "events_api_function_name" {
  description = "Events API Lambda function name"
  value       = module.compute.events_api_function_name
}

output "ecr_email_processor_url" {
  description = "ECR URL for email processor"
  value       = module.compute.ecr_email_processor_url
}

output "ecr_events_api_url" {
  description = "ECR URL for events API"
  value       = module.compute.ecr_events_api_url
}
