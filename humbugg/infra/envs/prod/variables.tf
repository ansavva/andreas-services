variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

# Stripe test-mode credentials, injected via TF_VAR_* in CI from GitHub environment
# secrets/vars — never committed. Empty defaults keep the parameters uncreated until
# the Stripe test account is provisioned (issue #123). Live-mode is blocked pending
# merchant-identity review (issue #159).

variable "stripe_publishable_key" {
  description = "Stripe test-mode publishable key (pk_test_...)"
  type        = string
  default     = ""
}

variable "stripe_secret_key" {
  description = "Stripe test-mode secret key (sk_test_...)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "stripe_webhook_secret" {
  description = "Stripe webhook signing secret (whsec_...)"
  type        = string
  default     = ""
  sensitive   = true
}
