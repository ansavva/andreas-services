variable "name" {
  description = "Name for the Cognito user pool"
  type        = string
}

variable "callback_urls" {
  description = "Allowed OAuth callback URLs for the user pool client"
  type        = list(string)
}

variable "logout_urls" {
  description = "Allowed logout URLs for the user pool client"
  type        = list(string)
}

variable "auth_domain" {
  description = "Custom domain for the Cognito managed login pages (e.g. scout-auth.andreas.services)"
  type        = string
}

variable "auth_certificate_arn" {
  description = "us-east-1 ACM certificate ARN covering auth_domain"
  type        = string
}

variable "route53_zone_id" {
  description = "Hosted zone for the auth domain's alias records"
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
