variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

# Injected via TF_VAR_alert_email in CI from the GitHub secret HUMBUGG_ALERT_EMAIL.
# Empty leaves the topic without a subscription so the stack applies before the
# secret exists — the same shape modules/billing uses for the Stripe parameters.
variable "alert_email" {
  description = "Address alarm notifications are emailed to. Empty creates no subscription."
  type        = string
  default     = ""
  sensitive   = true
}

variable "lambda_functions" {
  description = <<-EOT
    Lambdas to alarm on, keyed by the component name that goes into the alarm name.
    `error_threshold` is the Sum of AWS/Lambda Errors over one 5-minute period that
    trips the alarm; `throttle_alarm` adds a Throttles >= 1 alarm for that function.
  EOT
  type = map(object({
    function_name   = string
    error_threshold = number
    throttle_alarm  = optional(bool, false)
  }))
  default = {}
}

variable "api_ids" {
  description = "HTTP API ids to alarm on 5xx, keyed by the component name used in the alarm name."
  type        = map(string)
  default     = {}
}

variable "dynamodb_table_names" {
  description = "DynamoDB table names to alarm on read/write throttles, keyed by a short table label."
  type        = map(string)
  default     = {}
}

variable "api_5xx_threshold" {
  description = "Sum of API Gateway 5xx responses over one 5-minute period that trips the alarm."
  type        = number
  default     = 3
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
