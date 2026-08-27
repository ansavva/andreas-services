variable "name" {
  description = "Base name for the Cognito user pool"
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}

variable "auth_domain" {
  description = "Custom domain serving the hosted sign-in pages"
  type        = string
}

variable "auth_certificate_arn" {
  description = "ACM certificate for auth_domain — must live in us-east-1"
  type        = string
}

variable "route53_zone_id" {
  description = "Hosted zone holding the auth_domain alias records"
  type        = string
}

variable "callback_urls" {
  description = "Redirect URIs accepted after sign-in (exact match)"
  type        = list(string)
}

variable "logout_urls" {
  description = "Redirect URIs accepted after hosted sign-out (exact match)"
  type        = list(string)
}
