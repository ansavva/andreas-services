variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "humbugg_role_name" {
  description = "Existing Humbugg backend Lambda execution role"
  type        = string
  default     = "humbugg-prod-api-role"
}

# Where alarms mail. Arrives via TF_VAR_alert_email in CI from the GitHub secret
# MAILER_ALERT_EMAIL — never committed. Empty creates the SNS topic with no
# subscription, so the stack applies before the secret exists.
variable "alert_email" {
  description = "Address production alarm notifications are emailed to"
  type        = string
  default     = ""
  sensitive   = true
}
