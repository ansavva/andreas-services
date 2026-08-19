# Names match `envs/prod`'s outputs wherever the same thing exists in both, so
# the dev scripts and anything reading `terraform output -json` do not need to
# know which environment they are looking at.

output "resource_prefix" {
  description = "`studio-dev-<machine_short_id>` — the prefix every resource here is named from"
  value       = local.resource_prefix
}

output "machine_id" {
  description = "The machine UUID this environment is keyed by; echoed back so a script can confirm it applied the state it meant to"
  value       = var.machine_id
}

output "cognito_user_pool_id" {
  description = "Cognito user pool backing the local app"
  value       = module.auth.user_pool_id
}

output "cognito_user_pool_client_id" {
  description = "Cognito app client the local SPA signs in against"
  value       = module.auth.user_pool_client_id
}

output "media_bucket_name" {
  description = "The development media bucket, written by the seed script and read by the local API"
  value       = module.storage.media_bucket_name
}

output "media_uri" {
  description = "s3:// URI for the root of the development media tree"
  value       = module.storage.media_uri
}

output "catalog_table_name" {
  description = "The development catalog table the local API reads and writes"
  value       = module.storage.catalog_table_name
}
