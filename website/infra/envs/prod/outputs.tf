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

output "frontend_function_name" {
  description = "SSR frontend Lambda function name"
  value       = module.compute.frontend_function_name
}

output "api_ecr_repository_url" {
  value = module.compute.api_ecr_repository_url
}

output "frontend_ecr_repository_url" {
  value = module.compute.frontend_ecr_repository_url
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
