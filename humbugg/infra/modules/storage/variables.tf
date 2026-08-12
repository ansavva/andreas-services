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

# S3 bucket names are globally unique across all of AWS, so they alone carry a
# suffix. The region is deterministic and tells a reader something, which a
# random hash would not.
variable "aws_region" {
  description = "Region, used as the global-uniqueness suffix on bucket names"
  type        = string
}
