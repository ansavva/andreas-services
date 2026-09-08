variable "project" {
  description = "Project name, first segment of every resource name"
  type        = string
}

variable "environment" {
  description = "Deployment environment, second segment of every resource name"
  type        = string
}

variable "domain_name" {
  description = "Public host students open, e.g. classroom.andreas.services"
  type        = string
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID"
  type        = string
}

variable "lessons_bucket_regional_domain_name" {
  description = "Regional domain name of the lesson content bucket"
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
