# Names match `envs/prod`'s outputs wherever the same thing exists in both, so
# the dev scripts and anything reading `terraform output -json` do not need to
# know which environment they are looking at.

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

output "cognito_auth_domain" {
  description = "Managed login host the local SPA redirects to; `dev-setup.sh` writes it into frontend/.env.local as VITE_COGNITO_DOMAIN"
  value       = module.auth.auth_domain
}

output "media_bucket_name" {
  description = "The development media bucket, written by the seed script and read by the local API"
  value       = module.storage.media_bucket_name
}

output "catalog_table_name" {
  description = "The development catalog table the local API reads and writes"
  value       = module.storage.catalog_table_name
}

output "spa_ports" {
  description = <<-EOT
    The ports this stack will accept the SPA from — each a Cognito callback
    and a bucket CORS origin. `dev-up.sh` reads it and serves Vite on the first
    one that is free, so a stack applied with a different list is what decides,
    not the script's guess.
  EOT
  value       = var.spa_ports
}
