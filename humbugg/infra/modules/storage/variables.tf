variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}

variable "domain_name" {
  description = "Canonical application domain that app-bucket objects (e.g. avatars) are served from (CORS allow-list)"
  type        = string
}
