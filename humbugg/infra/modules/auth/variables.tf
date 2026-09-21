variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

# Matched character for character by Cognito, so both lists carry every literal
# redirect the app can produce — the https origin AND the humbugg:// custom scheme.
variable "callback_urls" {
  description = "Redirect URIs the Managed Login pages may return an authorization code to"
  type        = list(string)
  default     = []
}

variable "logout_urls" {
  description = "URIs the hosted /logout endpoint may return to"
  type        = list(string)
  default     = []
}

variable "auth_domain" {
  description = "Fully-qualified custom domain for the Managed Login pages. Mutually exclusive with auth_domain_prefix."
  type        = string
  default     = null
}

variable "auth_certificate_arn" {
  description = "us-east-1 ACM certificate covering auth_domain. Required with auth_domain."
  type        = string
  default     = null
}

variable "route53_zone_id" {
  description = "Hosted zone that holds auth_domain's alias records. Required with auth_domain."
  type        = string
  default     = null
}

variable "auth_domain_prefix" {
  description = "Prefix of a default <prefix>.auth.<region>.amazoncognito.com domain. Globally unique across AWS; mutually exclusive with auth_domain."
  type        = string
  default     = null
}

variable "email_sending_account" {
  description = "COGNITO_DEFAULT for development or DEVELOPER for production SES"
  type        = string
  default     = "COGNITO_DEFAULT"

  validation {
    condition     = contains(["COGNITO_DEFAULT", "DEVELOPER"], var.email_sending_account)
    error_message = "email_sending_account must be COGNITO_DEFAULT or DEVELOPER."
  }
}

variable "email_from_address" {
  description = "Verified From address used when Cognito sends through SES"
  type        = string
  default     = null
}

variable "email_source_arn" {
  description = "SES identity ARN used by production Cognito"
  type        = string
  default     = null
}

variable "email_configuration_set" {
  description = "SES configuration set used for Cognito feedback"
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}

# ---------------------------------------------------------------------------
# Social sign-in. Every provider is optional: an empty id leaves it uncreated
# and the button off the hosted page. `identity_providers.tf`.
# ---------------------------------------------------------------------------

variable "google_client_id" {
  description = "Google OAuth client id (Web application type). Empty disables Google."
  type        = string
  default     = ""
}

variable "google_client_secret" {
  description = "Google OAuth client secret. Required with google_client_id."
  type        = string
  default     = ""
  sensitive   = true
}

variable "facebook_app_id" {
  description = "Meta app id with Facebook Login enabled. Empty disables Facebook."
  type        = string
  default     = ""
}

variable "facebook_app_secret" {
  description = "Meta app secret. Required with facebook_app_id."
  type        = string
  default     = ""
  sensitive   = true
}

variable "apple_services_id" {
  description = "Sign in with Apple Services ID (the identifier, e.g. com.humbugg.auth). Empty disables Apple."
  type        = string
  default     = ""
}

variable "apple_team_id" {
  description = "Apple Developer Team ID. Required with apple_services_id."
  type        = string
  default     = ""
}

variable "apple_key_id" {
  description = "Key ID of the Sign in with Apple private key. Required with apple_services_id."
  type        = string
  default     = ""
}

variable "apple_private_key" {
  description = "The Sign in with Apple private key, PEM (.p8 contents). Required with apple_services_id."
  type        = string
  default     = ""
  sensitive   = true
}

variable "linkedin_client_id" {
  description = "LinkedIn app client id with the 'Sign In with LinkedIn using OpenID Connect' product. Empty disables LinkedIn."
  type        = string
  default     = ""
}

variable "linkedin_client_secret" {
  description = "LinkedIn app client secret. Required with linkedin_client_id."
  type        = string
  default     = ""
  sensitive   = true
}
