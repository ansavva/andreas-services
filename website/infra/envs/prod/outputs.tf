output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (for cache invalidation in CI)"
  value       = module.hosting.distribution_id
}

output "assets_bucket_name" {
  description = "S3 bucket for hashed client assets"
  value       = module.hosting.assets_bucket_name
}

output "api_function_name" {
  description = "Python API Lambda function name"
  value       = module.compute.api_function_name
}

output "www_function_name" {
  description = "SSR www Lambda function name"
  value       = module.compute.www_function_name
}

output "api_ecr_repository_url" {
  value = module.compute.api_ecr_repository_url
}

output "www_ecr_repository_url" {
  value = module.compute.www_ecr_repository_url
}

output "api_domain" {
  description = "Backend API custom domain"
  value       = "https://${module.api_domain.domain_name}/api"
}

output "cognito_user_pool_id" {
  value = module.auth.user_pool_id
}

output "cognito_user_pool_client_id" {
  value = module.auth.user_pool_client_id
}

output "cognito_auth_domain" {
  description = "Host serving the hosted sign-in pages"
  value       = module.auth.auth_domain
}

output "cognito_client_secret" {
  description = "Client secret for the www Lambda's code exchange"
  value       = module.auth.client_secret
  sensitive   = true
}

output "intake_table_name" {
  description = "Intake DynamoDB table name, passed to the API Lambda"
  value       = module.data.intake_table_name
}
