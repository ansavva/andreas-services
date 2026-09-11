output "api_function_name" {
  description = "Name of the classroom API Lambda"
  value       = aws_lambda_function.api.function_name
}

output "api_invoke_arn" {
  description = "Invoke ARN of the classroom API Lambda"
  value       = aws_lambda_function.api.invoke_arn
}

output "ecr_repository_url" {
  description = "URL of the API ECR repository"
  value       = var.create_ecr ? aws_ecr_repository.api[0].repository_url : ""
}
