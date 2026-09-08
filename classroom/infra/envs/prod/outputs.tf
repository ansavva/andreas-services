output "admin_url" {
  description = "Where a teacher signs in and manages her lessons"
  value       = "https://${local.admin_domain_name}"
}

output "lesson_base_url" {
  description = "Where students open a lesson; share links are built from this"
  value       = module.lesson_hosting.lesson_base_url
}

output "lessons_bucket" {
  description = "S3 bucket holding every lesson's uploaded files"
  value       = module.lessons.bucket_id
}

output "lesson_distribution_id" {
  description = "Lesson CloudFront distribution, for invalidating a re-uploaded lesson"
  value       = module.lesson_hosting.distribution_id
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
