output "email_processor_function_name" {
  description = "Email processor Lambda function name"
  value       = aws_lambda_function.email_processor.function_name
}

output "events_api_function_name" {
  description = "Events API Lambda function name"
  value       = aws_lambda_function.events_api.function_name
}

output "events_api_invoke_arn" {
  description = "Events API Lambda invoke ARN (for API Gateway integration)"
  value       = aws_lambda_function.events_api.invoke_arn
}

output "ecr_email_processor_url" {
  description = "ECR repository URL for email processor"
  value       = var.create_ecr ? aws_ecr_repository.email_processor[0].repository_url : null
}

output "ecr_events_api_url" {
  description = "ECR repository URL for events API"
  value       = var.create_ecr ? aws_ecr_repository.events_api[0].repository_url : null
}
