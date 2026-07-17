variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "callback_urls" {
  description = "Allowed browser callback URLs if a Cognito hosted flow is enabled"
  type        = list(string)
  default     = []
}

variable "logout_urls" {
  description = "Allowed browser logout URLs if a Cognito hosted flow is enabled"
  type        = list(string)
  default     = []
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
