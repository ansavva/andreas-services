output "resource_prefix" {
  value = local.resource_prefix
}

output "cognito_user_pool_id" {
  value = module.auth.user_pool_id
}

output "cognito_client_id" {
  value = module.auth.user_pool_client_id
}

output "cognito_auth_domain" {
  value = module.auth.auth_domain
}

output "table_names" {
  value = module.storage.table_names
}

output "app_bucket_name" {
  value = module.storage.app_bucket_name
}

output "machine_id" {
  value = var.machine_id
}
