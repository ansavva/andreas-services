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

output "cognito_auth_domain" {
  description = "Managed login host the local SPA redirects to; `dev-setup.sh` writes it into frontend/.env.local as VITE_COGNITO_DOMAIN"
  value       = module.auth.auth_domain
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

output "callback_base_url" {
  description = <<-EOT
    Where Replicate is told to call back for runs submitted against this stack.
    `dev-up.sh` exports it as `STUDIO_WEBHOOK_BASE_URL` for the local API.

    **Not the local API's own origin**, and it cannot be: Replicate cannot reach
    `http://localhost:8000`. This is a real AWS endpoint whose only job is to put
    the callback on the queue below, which this machine then drains.
  EOT
  value       = module.callbacks.base_url
}

output "callback_queue_url" {
  description = <<-EOT
    The queue this machine's callbacks land on. `dev-up.sh` exports it as
    `STUDIO_CALLBACK_QUEUE_URL` and runs a consumer that long-polls it and closes
    runs with the local working tree — which is the whole point of the split
    between receiving a callback and processing one.
  EOT
  value       = module.callbacks.queue_url
}

output "callback_dlq_url" {
  description = "Where a callback goes after five failed attempts against this machine's consumer"
  value       = module.callbacks.dlq_url
}

output "render_queue_url" {
  description = <<-EOT
    The queue this machine's render jobs land on. `dev-up.sh` exports it as
    `STUDIO_RENDER_QUEUE_URL` — read by the local API, which enqueues, and by the
    local consumer, which drains it and does the stitching with the working tree.

    **Both halves need it here**, unlike the callback queue, whose URL the prod
    API never sees because an event source mapping wires the worker to it. The
    thing that enqueues a render is the API.
  EOT
  value       = module.render.queue_url
}

output "render_dlq_url" {
  description = "Where a render job goes after five failed attempts against this machine's consumer"
  value       = module.render.dlq_url
}
