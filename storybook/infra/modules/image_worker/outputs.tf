# modules/image_worker/outputs.tf

output "lambda_function_name" {
  description = "Image normalization Lambda function name"
  value       = aws_lambda_function.worker.function_name
}

output "ecr_repository_url" {
  description = "ECR repository URL for the worker image"
  value       = aws_ecr_repository.worker.repository_url
}
