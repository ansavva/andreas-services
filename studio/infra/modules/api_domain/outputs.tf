output "domain_name" {
  description = "The API custom domain name"
  value       = aws_api_gateway_domain_name.main.domain_name
}

output "api_base_url" {
  description = "Public base URL of the backend API"
  value       = "https://${aws_api_gateway_domain_name.main.domain_name}"
}
