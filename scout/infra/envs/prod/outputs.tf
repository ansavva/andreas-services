output "api_endpoint" {
  description = "Public API URL"
  value       = module.api_gateway.invoke_url
}

output "s3_bucket" {
  description = "Frontend S3 bucket name"
  value       = module.storage.bucket_id
}

output "core_table_name" {
  description = "scout-prod-core DynamoDB table name"
  value       = module.data.core_table_name
}

output "settings_table_name" {
  description = "scout-prod-settings DynamoDB table name"
  value       = module.data.settings_table_name
}

output "artifacts_bucket" {
  description = "Source-run artifacts S3 bucket name"
  value       = module.artifacts_storage.bucket_id
}

output "images_bucket" {
  description = "Event images S3 bucket name"
  value       = module.images_storage.bucket_id
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = module.hosting.cloudfront_distribution_id
}

output "events_api_function_name" {
  description = "Events API Lambda function name"
  value       = module.compute.events_api_function_name
}

output "source_run_processor_function_name" {
  description = "Source-run processor Lambda function name"
  value       = module.compute.source_run_processor_function_name
}

output "scheduler_function_name" {
  description = "Scheduler Lambda function name"
  value       = module.compute.scheduler_function_name
}

output "sweep_function_name" {
  description = "Sweep Lambda function name"
  value       = module.compute.sweep_function_name
}

output "ecr_events_api_url" {
  description = "ECR URL for events API"
  value       = module.compute.ecr_events_api_url
}

output "cognito_user_pool_id" {
  description = "Cognito user pool ID for the admin console (VITE_COGNITO_USER_POOL_ID)"
  value       = module.auth.user_pool_id
}

output "cognito_user_pool_client_id" {
  description = "Cognito user pool client ID for the admin console (VITE_COGNITO_CLIENT_ID)"
  value       = module.auth.user_pool_client_id
}

output "cognito_auth_domain" {
  description = "Managed login host (VITE_COGNITO_DOMAIN)"
  value       = module.auth.auth_domain
}
