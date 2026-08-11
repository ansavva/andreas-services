variable "domain_name" {
  description = "Primary certificate domain name"
  type        = string
}

variable "subject_alternative_names" {
  description = "Additional hostnames covered by the certificate"
  type        = list(string)
}

variable "legacy_domain_name" {
  description = "Hostname whose validation record belongs in the legacy hosted zone"
  type        = string
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID owning the primary domain"
  type        = string
}

variable "legacy_route53_zone_id" {
  description = "Route53 hosted zone ID owning the legacy domain"
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
