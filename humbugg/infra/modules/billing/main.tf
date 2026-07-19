# Stripe billing configuration parameters.
#
# Secret values live in SSM (SecureString) and GitHub environment secrets — never
# in the repo. Each parameter is created only once a non-empty value is injected
# via TF_VAR_* in CI, so the stack remains deployable before the Stripe test
# account is provisioned (issue #123). Product/price IDs are wired directly to the
# Lambda as environment variables by the deploy workflow (they are not secrets).

locals {
  ssm_prefix = "/${var.project}/${var.environment}/stripe"
}

resource "aws_ssm_parameter" "publishable_key" {
  count = var.stripe_publishable_key != "" ? 1 : 0

  name        = "${local.ssm_prefix}/publishable-key"
  description = "Stripe test-mode publishable key for ${var.project}"
  type        = "String"
  value       = var.stripe_publishable_key
  tags        = var.tags
}

resource "aws_ssm_parameter" "secret_key" {
  count = var.stripe_secret_key != "" ? 1 : 0

  name        = "${local.ssm_prefix}/secret-key"
  description = "Stripe test-mode secret key for ${var.project}"
  type        = "SecureString"
  value       = var.stripe_secret_key
  tags        = var.tags
}

resource "aws_ssm_parameter" "webhook_secret" {
  count = var.stripe_webhook_secret != "" ? 1 : 0

  name        = "${local.ssm_prefix}/webhook-secret"
  description = "Stripe webhook signing secret for ${var.project}"
  type        = "SecureString"
  value       = var.stripe_webhook_secret
  tags        = var.tags
}
