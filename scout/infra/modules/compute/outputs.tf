output "events_api_function_name" {
  description = "Events API Lambda function name"
  value       = aws_lambda_function.events_api.function_name
}

output "events_api_invoke_arn" {
  description = "Events API Lambda invoke ARN (for API Gateway integration)"
  value       = aws_lambda_function.events_api.invoke_arn
}

output "source_run_processor_function_name" {
  description = "Source-run processor Lambda function name"
  value       = aws_lambda_function.source_run_processor.function_name
}

output "scheduler_function_name" {
  description = "Scheduler Lambda function name"
  value       = aws_lambda_function.scheduler.function_name
}

output "sweep_function_name" {
  description = "Sweep Lambda function name"
  value       = aws_lambda_function.sweep.function_name
}

output "source_renderer_function_name" {
  description = "Source renderer Lambda function name"
  value       = aws_lambda_function.source_renderer.function_name
}

output "ecr_renderer_url" {
  description = "ECR repository URL for the headless renderer"
  value       = var.create_ecr ? aws_ecr_repository.renderer[0].repository_url : null
}

output "ecr_events_api_url" {
  description = "ECR repository URL for events API"
  value       = var.create_ecr ? aws_ecr_repository.events_api[0].repository_url : null
}
