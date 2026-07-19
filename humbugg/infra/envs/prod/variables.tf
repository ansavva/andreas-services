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

variable "support_forward_to" {
  description = <<-EOT
    Private destination inbox for forwarded support@humbugg.com mail. This is a
    human-provided secret: leave empty in committed config and inject via
    TF_VAR_support_forward_to in CI (sourced from the SUPPORT_FORWARD_TO GitHub
    environment secret). Never commit the real address.
  EOT
  type        = string
  default     = ""
  sensitive   = true
}

variable "api_throttling_rate_limit" {
  description = "Steady-state requests/second for the backend API (API Gateway stage default throttling)."
  type        = number
  default     = 500
}

variable "api_throttling_burst_limit" {
  description = "Token-bucket burst capacity for the backend API stage default throttling."
  type        = number
  default     = 1000
}
