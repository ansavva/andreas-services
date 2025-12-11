output "frontend_url" {
  description = "Frontend URL"
  value       = "https://${var.app_subdomain}${var.frontend_path}"
}

output "backend_url" {
  description = "Backend API URL"
  value       = "https://${var.app_subdomain}${var.backend_path}"
}

output "app_url" {
  description = "Application base URL"
  value       = "https://${var.app_subdomain}"
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID for cache invalidation"
  value       = aws_cloudfront_distribution.app.id
}

output "s3_frontend_bucket" {
  description = "S3 bucket name for frontend"
  value       = aws_s3_bucket.frontend.id
}

output "s3_backend_bucket" {
  description = "S3 bucket name for backend files"
  value       = aws_s3_bucket.backend_files.id
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = aws_cognito_user_pool.main.id
}

output "cognito_user_pool_client_id" {
  description = "Cognito User Pool Client ID"
  value       = aws_cognito_user_pool_client.main.id
}

output "cognito_domain" {
  description = "Cognito domain"
  value       = "${aws_cognito_user_pool_domain.main.domain}.auth.${var.aws_region}.amazoncognito.com"
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.backend.function_name
}
