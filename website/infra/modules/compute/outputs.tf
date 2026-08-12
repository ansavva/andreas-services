output "api_invoke_arn" {
  description = "API Lambda invoke ARN for API Gateway integration"
  value       = aws_lambda_function.api.invoke_arn
}

output "api_function_name" {
  description = "API Lambda function name"
  value       = aws_lambda_function.api.function_name
}

output "www_function_name" {
  description = "SSR www Lambda function name"
  value       = aws_lambda_function.www.function_name
}

output "www_api_domain" {
  description = "SSR www HTTP API host (for the CloudFront origin), no scheme/path"
  value       = replace(aws_apigatewayv2_api.www.api_endpoint, "https://", "")
}

output "api_ecr_repository_url" {
  description = "ECR repo URL for the API image"
  value       = var.create_ecr ? aws_ecr_repository.api[0].repository_url : ""
}

output "www_ecr_repository_url" {
  description = "ECR repo URL for the www image"
  value       = var.create_ecr ? aws_ecr_repository.www[0].repository_url : ""
}
