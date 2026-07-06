output "api_invoke_arn" {
  description = "API Lambda invoke ARN for API Gateway integration"
  value       = aws_lambda_function.api.invoke_arn
}

output "api_function_name" {
  description = "API Lambda function name"
  value       = aws_lambda_function.api.function_name
}

output "frontend_function_name" {
  description = "SSR frontend Lambda function name"
  value       = aws_lambda_function.frontend.function_name
}

output "frontend_function_url" {
  description = "SSR frontend Lambda Function URL (https://<id>.lambda-url.<region>.on.aws/)"
  value       = aws_lambda_function_url.frontend.function_url
}

output "api_ecr_repository_url" {
  description = "ECR repo URL for the API image"
  value       = var.create_ecr ? aws_ecr_repository.api[0].repository_url : ""
}

output "frontend_ecr_repository_url" {
  description = "ECR repo URL for the frontend image"
  value       = var.create_ecr ? aws_ecr_repository.frontend[0].repository_url : ""
}
