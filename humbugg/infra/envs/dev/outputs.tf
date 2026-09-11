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

output "webhook_endpoint_url" {
  description = "This machine's public Stripe webhook URL; dev-aws-setup.sh registers it with Stripe."
  value       = module.webhook_relay.endpoint_url
}

output "webhook_queue_url" {
  description = "The queue behind that endpoint; the consumer dev-up.sh starts drains it."
  value       = module.webhook_relay.queue_url
}
