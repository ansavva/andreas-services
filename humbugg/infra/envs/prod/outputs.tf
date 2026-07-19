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

output "support_forwarder_lambda_function_name" {
  description = "Inbound support-forwarder Lambda function name"
  value       = module.support_forwarding.forwarder_lambda_function_name
}

output "support_inbound_bucket" {
  description = "S3 bucket holding raw inbound support mail"
  value       = module.support_forwarding.inbound_bucket
}

output "support_forward_to_ssm_parameter" {
  description = "SSM SecureString path holding the private support forward destination"
  value       = module.support_forwarding.forward_to_ssm_parameter
}
