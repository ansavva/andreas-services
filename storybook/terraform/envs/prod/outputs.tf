# envs/prod/outputs.tf

output "environment" {
  description = "Environment name"
  value       = local.environment
}

output "application_url" {
  description = "Application URL"
  value       = "https://${local.domain_name}/app"
}

output "api_url" {
  description = "API URL"
  value       = "https://${local.domain_name}/api"
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = module.auth.user_pool_id
}

output "cognito_user_pool_client_id" {
  description = "Cognito User Pool Client ID"
  value       = module.auth.user_pool_client_id
}

output "cognito_domain" {
  description = "Cognito domain"
  value       = module.auth.user_pool_domain
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = module.compute.lambda_function_name
}

output "image_worker_lambda_function_name" {
  description = "Image normalization Lambda function name"
  value       = module.image_worker.lambda_function_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = module.hosting.cloudfront_distribution_id
}

output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = module.compute.ecr_repository_url
}

output "image_worker_ecr_repository_url" {
  description = "ECR repository URL for image normalization worker"
  value       = module.image_worker.ecr_repository_url
}

output "s3_frontend_bucket" {
  description = "S3 frontend bucket"
  value       = module.storage.frontend_bucket_id
}

output "s3_backend_bucket" {
  description = "S3 backend files bucket"
  value       = module.storage.backend_files_bucket_id
}

output "image_queue_url" {
  description = "Image normalization SQS queue URL"
  value       = module.image_queue.queue_url
}

output "image_queue_arn" {
  description = "Image normalization SQS queue ARN"
  value       = module.image_queue.queue_arn
}

output "image_queue_dlq_url" {
  description = "Image normalization DLQ URL"
  value       = module.image_queue.dlq_url
}

output "image_queue_dlq_arn" {
  description = "Image normalization DLQ ARN"
  value       = module.image_queue.dlq_arn
}
