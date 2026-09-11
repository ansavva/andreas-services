# Names match `envs/prod`'s outputs wherever the same thing exists in both, so
# the dev scripts and anything reading `terraform output -json` do not need to
# know which environment they are looking at.

output "machine_id" {
  description = "The machine UUID this environment is keyed by; echoed back so a script can confirm it applied the state it meant to"
  value       = var.machine_id
}

output "resource_prefix" {
  description = "`classroom-dev-<short12>`, the prefix every resource here is named from"
  value       = local.resource_prefix
}

output "cognito_user_pool_id" {
  description = "Cognito user pool backing the local app; `dev-user.sh` creates its one account and `dev-up.sh` verifies tokens against it"
  value       = module.auth.user_pool_id
}

output "cognito_client_id" {
  description = "Cognito app client the local SPA signs in against"
  value       = module.auth.user_pool_client_id
}

output "cognito_domain" {
  description = "Managed Login host the local SPA redirects to; `dev-setup.sh` writes it into frontend/.env.local as VITE_COGNITO_DOMAIN"
  value       = module.auth.auth_domain
}

output "pages_table_name" {
  description = "The development pages table the local API reads and writes"
  value       = module.data.pages_table_name
}

output "spa_origin" {
  description = "The origin registered on the app client; `dev-up.sh` serves the SPA here and a mismatch fails at the redirect"
  value       = var.spa_origin
}

output "lessons_bucket_name" {
  description = "This machine's lesson bucket; `dev-up.sh` exports it as CLASSROOM_LESSONS_BUCKET"
  value       = module.lessons.bucket_id
}
