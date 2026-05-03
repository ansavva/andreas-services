output "domain_name" {
  description = "API Gateway custom domain name"
  value       = aws_api_gateway_domain_name.main.domain_name
}

output "regional_domain_name" {
  description = "Regional domain name for the API Gateway domain"
  value       = aws_api_gateway_domain_name.main.regional_domain_name
}

output "regional_zone_id" {
  description = "Regional hosted zone ID for the API Gateway domain"
  value       = aws_api_gateway_domain_name.main.regional_zone_id
}
