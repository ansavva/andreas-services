output "api_url" {
  value = module.platform.api_url
}

output "ecr_repository_url" {
  value = module.platform.ecr_repository_url
}

output "lambda_function_names" {
  value = module.platform.lambda_function_names
}

output "content_bucket" {
  value = module.platform.content_bucket
}

output "messages_table" {
  value = module.platform.messages_table
}

output "suppressions_table" {
  value = module.platform.suppressions_table
}

output "service_registry_json" {
  value = module.platform.service_registry_json
}

output "configuration_set_registry_json" {
  value = module.platform.configuration_set_registry_json
}

output "humbugg_status_queue_url" {
  value = module.platform.humbugg_status_queue_url
}

output "humbugg_status_queue_arn" {
  value = module.platform.humbugg_status_queue_arn
}

output "humbugg_auth_configuration_set" {
  value = module.platform.humbugg_auth_configuration_set
}
