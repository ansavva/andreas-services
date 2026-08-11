output "domain_name" {
  description = "Custom API domain name"
  value       = aws_apigatewayv2_domain_name.api.domain_name
}

output "api_base_url" {
  description = "HTTPS base URL callers should use for the API"
  value       = "https://${aws_apigatewayv2_domain_name.api.domain_name}"
}

output "regional_domain_name" {
  description = "Regional API Gateway hostname the Route53 aliases point at"
  value       = aws_apigatewayv2_domain_name.api.domain_name_configuration[0].target_domain_name
}
