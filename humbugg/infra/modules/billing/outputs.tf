output "stripe_ssm_prefix" {
  description = "SSM path prefix under which Stripe parameters are stored"
  value       = local.ssm_prefix
}

output "stripe_secret_key_parameter_name" {
  description = "SSM parameter name for the Stripe secret key (empty until provisioned)"
  value       = try(aws_ssm_parameter.secret_key[0].name, "")
}

output "stripe_webhook_secret_parameter_name" {
  description = "SSM parameter name for the Stripe webhook secret (empty until provisioned)"
  value       = try(aws_ssm_parameter.webhook_secret[0].name, "")
}
