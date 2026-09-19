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


# Where production alarms mail. Arrives via TF_VAR_alert_email in CI from the GitHub
# secret HUMBUGG_ALERT_EMAIL — never committed. Empty creates the SNS topic with no
# subscription, so the stack applies before the secret exists.
variable "alert_email" {
  description = "Address production alarm notifications are emailed to"
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

# Social sign-in credentials, injected via TF_VAR_* in CI from the
# humbugg-production environment — never committed. An empty id leaves that
# provider uncreated and its button off the hosted page, so the stack applies
# before any console work is done and each provider lands as its secret does.
# `docs/auth-social-login.md` is the console-by-console walk.

variable "google_client_id" {
  description = "Google OAuth client id"
  type        = string
  default     = ""
}

variable "google_client_secret" {
  description = "Google OAuth client secret"
  type        = string
  default     = ""
  sensitive   = true
}

variable "facebook_app_id" {
  description = "Meta app id"
  type        = string
  default     = ""
}

variable "facebook_app_secret" {
  description = "Meta app secret"
  type        = string
  default     = ""
  sensitive   = true
}

variable "apple_services_id" {
  description = "Sign in with Apple Services ID"
  type        = string
  default     = ""
}

variable "apple_team_id" {
  description = "Apple Developer Team ID"
  type        = string
  default     = ""
}

variable "apple_key_id" {
  description = "Sign in with Apple key id"
  type        = string
  default     = ""
}

variable "apple_private_key" {
  description = "Sign in with Apple private key (.p8 contents)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "linkedin_client_id" {
  description = "LinkedIn client id"
  type        = string
  default     = ""
}

variable "linkedin_client_secret" {
  description = "LinkedIn client secret"
  type        = string
  default     = ""
  sensitive   = true
}
