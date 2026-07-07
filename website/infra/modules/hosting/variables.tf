variable "www_domain" {
  description = "Canonical host (e.g. www.andreas.services)"
  type        = string
}

variable "apex_domain" {
  description = "Apex host that 301-redirects to www (e.g. andreas.services)"
  type        = string
}

variable "assets_bucket_name" {
  description = "S3 bucket name for hashed client assets"
  type        = string
}

variable "frontend_api_domain" {
  description = "SSR HTTP API host used as the CloudFront default origin (no scheme)"
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
