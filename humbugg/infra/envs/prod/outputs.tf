output "api_endpoint" {
  description = "API Gateway invoke URL"
  value       = module.compute.api_endpoint
}

output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = module.compute.ecr_repository_url
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = module.compute.lambda_function_name
}

output "email_status_lambda_function_name" {
  description = "Mailer status consumer Lambda function name"
  value       = module.compute.email_status_lambda_function_name
}

output "frontend_ecr_repository_url" {
  description = "SSR frontend ECR repository URL"
  value       = module.compute.frontend_ecr_repository_url
}

output "frontend_lambda_function_name" {
  description = "SSR frontend Lambda function name"
  value       = module.compute.frontend_lambda_function_name
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = module.auth.user_pool_id
}

output "cognito_client_id" {
  description = "Cognito User Pool Client ID"
  value       = module.auth.user_pool_client_id
}

output "s3_frontend_bucket" {
  description = "Frontend S3 bucket name"
  value       = module.storage.bucket_id
}

output "app_bucket" {
  description = "Application object S3 bucket name (holds avatars under the avatars/ prefix)"
  value       = module.storage.app_bucket_id
}

output "api_domain" {
  description = "Public base URL of the backend API on its own domain"
  value       = module.api_domain.api_base_url
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = module.hosting.cloudfront_distribution_id
}

output "email_from_address" {
  description = "Verified transactional email From address"
  value       = module.email.from_address
}

output "ses_identity_arn" {
  description = "Verified SES domain identity ARN"
  value       = module.email.identity_arn
}
