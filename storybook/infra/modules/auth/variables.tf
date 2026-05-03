# modules/auth/variables.tf

variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "callback_urls" {
  description = "List of callback URLs for Cognito"
  type        = list(string)
}

variable "logout_urls" {
  description = "List of logout URLs for Cognito"
  type        = list(string)
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
