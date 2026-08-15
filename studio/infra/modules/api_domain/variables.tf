variable "domain_name" {
  description = "Custom domain for the API (e.g. studio-api.andreas.services)"
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
