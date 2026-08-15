variable "project" {
  description = "Project name; the first segment of every resource name"
  type        = string
}

variable "environment" {
  description = "Deployment environment; the second segment of every resource name"
  type        = string
}

variable "domain_name" {
  description = "Public hostname for the app (e.g. studio.andreas.services)"
  type        = string
}

variable "app_bucket_name" {
  description = "Globally unique S3 bucket name for the built SPA"
  type        = string
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID for andreas.services"
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
