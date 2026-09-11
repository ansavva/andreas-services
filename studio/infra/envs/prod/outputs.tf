output "app_bucket_name" {
  description = "S3 bucket the deploy workflow syncs the built SPA into"
  value       = module.hosting.app_bucket_id
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (for cache invalidation in CI)"
  value       = module.hosting.distribution_id
}

output "api_domain" {
  description = "Backend API base URL"
  value       = module.api_domain.api_base_url
}

output "cognito_user_pool_id" {
  description = "Cognito user pool backing the app"
  value       = module.auth.user_pool_id
}

output "cognito_user_pool_client_id" {
  description = "Cognito app client the SPA signs in against"
  value       = module.auth.user_pool_client_id
}

output "cognito_auth_domain" {
  description = "Managed login host the SPA redirects to; the deploy workflow writes it to /studio/prod/cognito-auth-domain and builds the SPA with it as VITE_COGNITO_DOMAIN"
  value       = module.auth.auth_domain
}

output "media_bucket_name" {
  description = "The media bucket the pipeline writes and the API reads"
  value       = module.media.bucket_name
}

output "catalog_table_name" {
  description = <<-EOT
    The catalog table the API reads and writes. The deploy workflow writes it to
    `/studio/prod/catalog-table` and `update-lambda` reads it back — the same
    route `media_bucket_name` takes, and the only one that works: the Lambda's
    `environment` block is `ignore_changes`, so SSM is what actually carries a
    Terraform value to a running function.
  EOT
  value       = module.catalog.table_name
}

output "callback_base_url" {
  description = <<-EOT
    Origin Replicate is told to call back on. The deploy workflow writes it to
    `/studio/prod/callback-base-url` and `update-lambda` reads it back as
    `STUDIO_WEBHOOK_BASE_URL` — the same route the media bucket and the catalog
    table take, and here it is the only one available: `modules/compute` lends
    the callback worker its execution role, so it cannot also read that module's
    output without a cycle.
  EOT
  value       = module.callbacks.base_url
}

output "callback_queue_url" {
  description = "The queue a received callback lands on, drained by the worker Lambda"
  value       = module.callbacks.queue_url
}

output "callback_worker_function_name" {
  description = "The queue consumer; the deploy workflow pins its image alongside the API's"
  value       = module.callbacks.worker_function_name
}

output "replicate_token_parameter" {
  description = <<-EOT
    The SecureString the API and the worker read the provider token from.
    **Terraform creates it and never holds its value** — set it out of band with
    `aws ssm put-parameter --overwrite --type SecureString`.
  EOT
  value       = aws_ssm_parameter.replicate_api_token.name
}

output "render_queue_url" {
  description = <<-EOT
    The queue the API enqueues render jobs onto. `deploy-infra` writes it to SSM
    and `update-lambda` sets it on the API Lambda as `STUDIO_RENDER_QUEUE_URL`.

    **Read by the API, unlike the callback queue's URL**, which the API never
    needs: a callback arrives at its own gateway and the worker is wired by an
    event source mapping. A render is asked for by the API, so the API is what
    holds this.
  EOT
  value       = module.render.queue_url
}

output "render_worker_function_name" {
  description = "The render worker; the deploy workflow pins its image the way it pins the other two."
  value       = module.render.worker_function_name
}
