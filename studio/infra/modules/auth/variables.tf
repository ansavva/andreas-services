variable "name" {
  description = "Base name for the Cognito user pool"
  type        = string
}

variable "callback_urls" {
  description = "Allowed OAuth callback URLs for the user pool client. Cognito matches these character for character."
  type        = list(string)
}

variable "logout_urls" {
  description = "Allowed post-sign-out redirect URLs for the user pool client"
  type        = list(string)
}

# Exactly one of the next two. Enforced by a precondition on the domain
# resource in main.tf, because variable validation cannot read a sibling.

variable "auth_domain" {
  description = "Custom host for the Cognito managed login pages (e.g. studio-auth.andreas.services). Empty for a default Cognito domain."
  type        = string
  default     = ""
}

variable "auth_domain_prefix" {
  description = "Prefix for a default Cognito domain, giving <prefix>.auth.<region>.amazoncognito.com. Empty when auth_domain is set."
  type        = string
  default     = ""
}

variable "auth_certificate_arn" {
  description = "us-east-1 ACM certificate ARN covering auth_domain. Required with auth_domain, unused without it."
  type        = string
  default     = ""
}

variable "route53_zone_id" {
  description = "Hosted zone for the auth host's alias records. Required with auth_domain, unused without it."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
