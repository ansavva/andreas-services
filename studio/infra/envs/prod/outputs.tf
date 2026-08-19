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

output "media_bucket_name" {
  description = "The media bucket the pipeline writes and the API reads"
  value       = module.media.bucket_name
}

output "media_uri" {
  description = "s3:// URI for the root of the media tree"
  value       = module.media.media_uri
}

output "catalog_table_name" {
  description = <<-EOT
    The catalog table the API reads and writes. The deploy workflow writes it to
    `/studio/prod/catalog-table` and `update-lambda` reads it back — the same
    route `media_bucket_name` takes, and the only one that works: the Lambda's
    `environment` block is `ignore_changes`, so SSM is what actually carries a
    Terraform value to a running function.
  EOT
  value       = module.catalog.table_name
}
