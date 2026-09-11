output "domain_name" {
  description = "The API custom domain name"
  value       = aws_api_gateway_domain_name.main.domain_name
}
