output "user_pool_id" {
  description = "Cognito user pool ID"
  value       = aws_cognito_user_pool.main.id
}

output "user_pool_arn" {
  description = "Cognito user pool ARN"
  value       = aws_cognito_user_pool.main.arn
}

output "user_pool_client_id" {
  description = "Cognito user pool app client ID"
  value       = aws_cognito_user_pool_client.main.id
}

# The full HOST the SPA redirects to, which is what VITE_COGNITO_DOMAIN wants.
# A custom domain is already a host; a default one is only the prefix, so the
# rest is composed here rather than in every caller.
output "auth_domain" {
  description = "Managed Login host the SPA redirects to (VITE_COGNITO_DOMAIN)"
  value = (
    var.auth_domain != ""
    ? aws_cognito_user_pool_domain.main.domain
    : "${aws_cognito_user_pool_domain.main.domain}.auth.${data.aws_region.current.region}.amazoncognito.com"
  )
}
