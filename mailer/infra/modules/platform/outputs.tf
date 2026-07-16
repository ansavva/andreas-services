output "api_url" {
  value = "https://${var.domain_name}"
}

output "ecr_repository_url" {
  value = aws_ecr_repository.mailer.repository_url
}

output "lambda_function_names" {
  value = {
    ingress  = aws_lambda_function.ingress.function_name
    sender   = aws_lambda_function.sender.function_name
    feedback = aws_lambda_function.feedback.function_name
  }
}

output "content_bucket" {
  value = aws_s3_bucket.content.id
}

output "messages_table" {
  value = aws_dynamodb_table.messages.name
}

output "suppressions_table" {
  value = aws_dynamodb_table.suppressions.name
}

output "service_registry_json" {
  value = local.service_registry_json
}

output "configuration_set_registry_json" {
  value = local.configuration_set_registry_json
}

output "humbugg_status_queue_url" {
  value = aws_sqs_queue.humbugg_status.url
}

output "humbugg_status_queue_arn" {
  value = aws_sqs_queue.humbugg_status.arn
}

output "humbugg_auth_configuration_set" {
  value = local.humbugg_auth_config_set
}
