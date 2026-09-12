output "api_id" {
  description = "WebSocket API id, for mapping a custom domain onto it"
  value       = aws_apigatewayv2_api.realtime.id
}

output "stage_name" {
  description = "WebSocket API stage name, for the custom-domain API mapping"
  value       = aws_apigatewayv2_stage.realtime.name
}

output "management_endpoint" {
  description = "The HTTPS endpoint the backend posts to connections through (the stage's execute-api URL)"
  value       = "https://${aws_apigatewayv2_api.realtime.id}.execute-api.${var.aws_region}.amazonaws.com/${aws_apigatewayv2_stage.realtime.name}"
}

output "authorizer_lambda_function_name" {
  description = "The $connect authorizer Lambda"
  value       = aws_lambda_function.authorizer.function_name
}

output "connections_lambda_function_name" {
  description = "The $connect/$disconnect/$default handler Lambda"
  value       = aws_lambda_function.connections.function_name
}
