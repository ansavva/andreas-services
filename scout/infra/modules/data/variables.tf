variable "project" {
  description = "Project name, first segment of every resource name"
  type        = string
}

variable "environment" {
  description = "Deployment environment, second segment of every resource name (prod/dev)"
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
