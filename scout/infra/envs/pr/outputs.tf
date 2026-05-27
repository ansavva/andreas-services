output "api_endpoint" {
  description = "PR API endpoint URL"
  value       = module.api_gateway.invoke_url
}

output "user_pool_id" {
  description = "Cognito User Pool ID"
  value       = module.auth.user_pool_id
}

output "user_pool_client_id" {
  description = "Cognito User Pool Client ID"
  value       = module.auth.user_pool_client_id
}

output "frontend_url" {
  description = "PR preview frontend URL"
  value       = "https://scout-pr.andreas.services/${var.pr_number}/app"
}
