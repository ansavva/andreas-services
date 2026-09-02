output "user_pool_id" {
  description = "Cognito User Pool ID"
  value       = aws_cognito_user_pool.main.id
}

output "user_pool_client_id" {
  description = "Cognito User Pool Client ID"
  value       = aws_cognito_user_pool_client.main.id
}

# The host, never a URL — the app builds /oauth2/authorize, /oauth2/token,
# /oauth2/revoke and /logout from it. A default domain's host is not an attribute
# of the resource, only its prefix is, so it is spelled out here.
output "auth_domain" {
  description = "Host serving the Managed Login pages"
  value = (
    var.auth_domain != null
    ? aws_cognito_user_pool_domain.main.domain
    : "${aws_cognito_user_pool_domain.main.domain}.auth.${data.aws_region.current.region}.amazoncognito.com"
  )
}

output "user_pool_arn" {
  description = "Cognito User Pool ARN, for the least-privilege AdminGetUser grant the API needs"
  value       = aws_cognito_user_pool.main.arn
}
