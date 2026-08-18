output "app_url" {
  description = "Public URL of the studio app"
  value       = module.hosting.app_url
}

output "app_bucket_name" {
  description = "S3 bucket the deploy workflow syncs the built SPA into"
  value       = module.hosting.app_bucket_id
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (for cache invalidation in CI)"
  value       = module.hosting.distribution_id
}

output "api_function_name" {
  description = "API Lambda function name"
  value       = module.compute.api_function_name
}

output "api_ecr_repository_url" {
  description = "ECR repository the deploy workflow pushes the API image to"
  value       = module.compute.ecr_repository_url
}

output "api_domain" {
  description = "Backend API base URL"
  value       = module.api_domain.api_base_url
}

output "cognito_user_pool_id" {
  description = "Cognito user pool backing the app"
  value       = module.auth.user_pool_id
}

output "cognito_user_pool_client_id" {
  description = "Cognito app client the SPA signs in against"
  value       = module.auth.user_pool_client_id
}

# The bucket currently IN SERVICE — which during the rename is not necessarily
# the correctly-named one. The deploy workflow copies this into
# `/studio/prod/media-bucket`, and the skills and `dev-setup.sh` read it from
# there, so this output is what actually moves the pipeline across.
output "media_bucket_name" {
  description = "The media bucket the pipeline writes and the API reads"
  value       = local.active_media.bucket_name
}

output "media_uri" {
  description = "s3:// URI for the root of the media tree"
  value       = local.active_media.media_uri
}

output "media_archive_bucket_name" {
  description = "The retained original media bucket — holds the version history the live bucket's copy does not carry"
  value       = module.media_archive.bucket_name
}
