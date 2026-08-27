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

# The full host, whichever form the domain took, so a caller never has to know
# which one it passed in. This is `VITE_COGNITO_DOMAIN`; the SPA builds
# `https://<host>/oauth2/authorize` and `/logout` from it.
output "auth_domain" {
  description = "Managed login host the SPA redirects to (VITE_COGNITO_DOMAIN)"
  value = (
    var.auth_domain != ""
    ? aws_cognito_user_pool_domain.main.domain
    : "${aws_cognito_user_pool_domain.main.domain}.auth.${data.aws_region.current.region}.amazoncognito.com"
  )
}
