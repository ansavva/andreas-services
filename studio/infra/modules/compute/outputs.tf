output "api_function_name" {
  description = "Name of the API Lambda; the deploy workflow updates its code and env"
  value       = aws_lambda_function.api.function_name
}

output "api_invoke_arn" {
  description = "Invoke ARN wired into the API Gateway integration"
  value       = aws_lambda_function.api.invoke_arn
}

output "api_role_arn" {
  description = "ARN of the API Lambda's execution role"
  value       = aws_iam_role.api.arn
}

output "ecr_repository_url" {
  description = "ECR repository the deploy workflow pushes the API image to"
  value       = var.create_ecr ? aws_ecr_repository.api[0].repository_url : ""
}

output "api_role_name" {
  description = <<-EOT
    Name of the API Lambda's execution role. **The callback worker runs under
    this same role**: it does exactly what the API does — the media bucket, the
    catalog, the provider token — so a role of its own would be a hand-kept copy
    of these policies that eventually drifts. `modules/callbacks` attaches one
    extra inline policy to it for the queue.
  EOT
  value       = aws_iam_role.api.name
}
