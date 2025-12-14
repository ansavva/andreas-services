# envs/dev/outputs.tf

output "environment" {
  description = "Environment name"
  value       = local.environment
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = module.auth.user_pool_id
}

output "cognito_user_pool_client_id" {
  description = "Cognito User Pool Client ID"
  value       = module.auth.user_pool_client_id
}

output "cognito_domain" {
  description = "Cognito domain"
  value       = module.auth.user_pool_domain
}

output "setup_instructions" {
  description = "Instructions for local development setup"
  value       = <<-EOT
    Development environment deployed successfully!

    Next steps:
    1. Start MongoDB: docker-compose up -d mongodb

    2. Copy backend/.env.example to backend/.env and set:
       - AWS_COGNITO_USER_POOL_ID=${module.auth.user_pool_id}
       - AWS_COGNITO_APP_CLIENT_ID=${module.auth.user_pool_client_id}
       - MONGODB_URL=mongodb://localhost:27017/storybook_dev
       - STORAGE_TYPE=filesystem
       - FILE_STORAGE_PATH=./storage

    3. Copy frontend/.env.local.example to frontend/.env.local and set:
       - VITE_AWS_COGNITO_USER_POOL_ID=${module.auth.user_pool_id}
       - VITE_AWS_COGNITO_APP_CLIENT_ID=${module.auth.user_pool_client_id}
       - VITE_AWS_COGNITO_DOMAIN=${module.auth.user_pool_domain}

    Run local backend: python -m src.app
    Run local frontend: npm run dev
  EOT
}
