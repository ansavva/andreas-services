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

# --- the sign-in host, one of two shapes ----------------------------------
#
# `envs/prod` sets `auth_domain` — a name on the shared wildcard certificate,
# with the alias record below pointing at it. `envs/dev` sets
# `auth_domain_prefix` instead and gets `<prefix>.auth.<region>.amazoncognito.com`,
# because a per-machine stack has no certificate and no DNS of its own and a
# custom domain would add a ~15-minute apply each way for pages one developer
# ever loads. Exactly one of the two, enforced at plan time in main.tf.

variable "auth_domain" {
  description = "Custom domain for Cognito Managed Login. Mutually exclusive with auth_domain_prefix."
  type        = string
  default     = ""
}

variable "auth_domain_prefix" {
  description = "Default Cognito domain prefix, globally unique across AWS. Mutually exclusive with auth_domain."
  type        = string
  default     = ""
}

variable "auth_certificate_arn" {
  description = "us-east-1 ACM certificate ARN for the auth domain. Required with auth_domain."
  type        = string
  default     = ""
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID. Required with auth_domain."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
