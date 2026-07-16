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

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
