variable "project" {
  description = "Project name; the first segment of every resource name"
  type        = string
}

variable "environment" {
  description = "Deployment environment; the second segment of every resource name"
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
