output "user_pool_id" {
  description = "Cognito User Pool ID"
  value       = aws_cognito_user_pool.main.id
}

output "user_pool_arn" {
  description = "Cognito User Pool ARN (for the API Gateway authorizer)"
  value       = aws_cognito_user_pool.main.arn
}

output "user_pool_client_id" {
  description = "Cognito User Pool Client ID"
  value       = aws_cognito_user_pool_client.main.id
}

output "auth_domain" {
  description = "Host serving the hosted sign-in pages"
  value       = aws_cognito_user_pool_domain.main.domain
}

output "client_secret" {
  description = "Client secret for the server-side code exchange"
  value       = aws_cognito_user_pool_client.main.client_secret
  sensitive   = true
}
