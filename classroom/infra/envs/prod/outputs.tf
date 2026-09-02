output "site_url" {
  description = "Public site URL"
  value       = "https://${local.domain_name}"
}

output "api_url" {
  description = "Public API base URL"
  value       = module.api_gateway.invoke_url
}

output "frontend_bucket" {
  description = "S3 bucket holding the built SPA"
  value       = module.storage.bucket_id
}

output "distribution_id" {
  description = "CloudFront distribution ID, for cache invalidation"
  value       = module.hosting.distribution_id
}

output "ecr_repository_url" {
  description = "ECR repository for the API image"
  value       = module.compute.ecr_repository_url
}

output "cognito_user_pool_id" {
  description = "Cognito user pool ID, for provisioning teacher accounts"
  value       = module.auth.user_pool_id
}

output "cognito_client_id" {
  description = "Cognito app client ID used by the SPA"
  value       = module.auth.user_pool_client_id
}

output "cognito_domain" {
  description = "Managed Login domain"
  value       = module.auth.auth_domain
}
