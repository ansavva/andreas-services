output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.backend.function_name
}

output "email_status_lambda_function_name" {
  description = "Mailer status consumer Lambda function name"
  value       = aws_lambda_function.email_status.function_name
}

output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.backend.repository_url
}

output "frontend_ecr_repository_url" {
  description = "SSR frontend ECR repository URL"
  value       = aws_ecr_repository.frontend.repository_url
}

output "frontend_lambda_function_name" {
  description = "SSR frontend Lambda function name"
  value       = aws_lambda_function.frontend.function_name
}

output "frontend_api_domain" {
  description = "SSR frontend HTTP API host without a scheme"
  value       = replace(aws_apigatewayv2_api.frontend.api_endpoint, "https://", "")
}

output "api_endpoint" {
  description = "API Gateway invoke URL"
  value       = aws_apigatewayv2_stage.backend.invoke_url
}
