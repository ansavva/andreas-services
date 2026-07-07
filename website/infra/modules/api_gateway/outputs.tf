output "rest_api_id" {
  description = "REST API ID"
  value       = aws_api_gateway_rest_api.main.id
}

output "stage_name" {
  description = "Deployed stage name"
  value       = aws_api_gateway_stage.main.stage_name
}

output "invoke_url" {
  description = "Default execute-api invoke URL for the stage"
  value       = aws_api_gateway_stage.main.invoke_url
}
