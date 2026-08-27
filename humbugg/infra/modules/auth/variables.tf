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
