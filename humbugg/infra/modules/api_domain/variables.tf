variable "domain_name" {
  description = "Custom domain for the API (e.g. api.humbugg.com)"
  type        = string
}

variable "certificate_arn" {
  description = "ARN of a validated certificate in the API's own region covering the domain"
  type        = string
}

variable "api_id" {
  description = "ID of the HTTP API the domain maps onto"
  type        = string
}

variable "stage_name" {
  description = "Name of the HTTP API stage the domain maps onto"
  type        = string
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID for the domain"
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
