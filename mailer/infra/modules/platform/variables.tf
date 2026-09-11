variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "domain_name" {
  type = string
}

variable "route53_zone_id" {
  type = string
}

variable "humbugg_role_name" {
  type = string
}

variable "humbugg_sender_address" {
  type = string
}

# Where alarms mail. Injected via TF_VAR_alert_email in CI from the GitHub secret
# MAILER_ALERT_EMAIL. Empty creates the topic with no subscription, so the stack
# applies before the secret exists.
variable "alert_email" {
  description = "Address alarm notifications are emailed to. Empty creates no subscription."
  type        = string
  default     = ""
  sensitive   = true
}

variable "tags" {
  type = map(string)
}
