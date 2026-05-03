variable "pr_number" {
  description = "PR number (empty string for non-PR environments)"
  type        = string
  default     = ""
}

variable "dynamodb_table_arn" {
  description = "DynamoDB events table ARN"
  type        = string
}

variable "events_table_name" {
  description = "DynamoDB events table name"
  type        = string
}

variable "email_processor_image_uri" {
  description = "ECR image URI for the email processor Lambda"
  type        = string
}

variable "events_api_image_uri" {
  description = "ECR image URI for the events API Lambda"
  type        = string
}

variable "email_processor_env_vars" {
  description = "Environment variables for the email processor Lambda"
  type        = map(string)
  sensitive   = true
  default     = {}
}

variable "create_ecr" {
  description = "Whether to create ECR repositories (false for PR environments)"
  type        = bool
  default     = true
}

variable "create_eventbridge" {
  description = "Whether to create the EventBridge schedule rule (false for PR environments)"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
