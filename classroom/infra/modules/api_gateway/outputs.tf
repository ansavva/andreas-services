output "api_id" {
  description = "REST API ID"
  value       = aws_api_gateway_rest_api.main.id
}

output "invoke_url" {
  description = "Public API URL via custom domain"
  value       = var.base_path != "" ? "https://${var.custom_domain_name}/${var.base_path}/api" : "https://${var.custom_domain_name}/api"
}

output "execute_api_url" {
  description = "Raw execute-api URL (for CloudFront origin)"
  value       = "https://${aws_api_gateway_rest_api.main.id}.execute-api.${data.aws_region.current.region}.amazonaws.com/${var.stage_name}"
}

data "aws_region" "current" {}
