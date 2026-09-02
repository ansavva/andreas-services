variable "name" {
  description = "Name prefix for the user pool and its client"
  type        = string
}

variable "callback_urls" {
  description = "Exact OAuth callback URLs, character for character"
  type        = list(string)
}

variable "logout_urls" {
  description = "Exact post-sign-out URLs"
  type        = list(string)
}

variable "auth_domain" {
  description = "Custom domain for Cognito Managed Login"
  type        = string
}

variable "auth_certificate_arn" {
  description = "us-east-1 ACM certificate ARN for the auth domain"
  type        = string
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID"
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
