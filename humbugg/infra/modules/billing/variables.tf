variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

# Stripe test-mode credentials. Values are injected via TF_VAR_* in CI from GitHub
# environment secrets/vars and are never committed. Empty defaults keep the SSM
# parameters uncreated until real test-mode credentials are provisioned, so the
# stack stays deployable before the Stripe test account exists (issue #123).
#
# Live-mode credentials are intentionally unsupported here: activation is blocked
# pending merchant-identity review (issue #159).

variable "stripe_publishable_key" {
  description = "Stripe test-mode publishable key (pk_test_...). Not secret, but versioned alongside the secrets."
  type        = string
  default     = ""
}

variable "stripe_secret_key" {
  description = "Stripe test-mode secret key (sk_test_...)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "stripe_webhook_secret" {
  description = "Stripe webhook signing secret (whsec_...)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
