output "cognito_user_pool_id" {
  description = "Cognito user pool the library's membership rows are keyed by"
  value       = module.auth.user_pool_id
}

output "cognito_user_pool_client_id" {
  description = "The pool's SPA client; `studio --profile prod` still signs in against it"
  value       = module.auth.user_pool_client_id
}

output "cognito_auth_domain" {
  description = "The pool's managed login host"
  value       = module.auth.auth_domain
}

output "media_bucket_name" {
  description = "The media bucket — the library's bytes"
  value       = module.media.bucket_name
}

output "catalog_table_name" {
  description = "The catalog table — the library's rows"
  value       = module.catalog.table_name
}
