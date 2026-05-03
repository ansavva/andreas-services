variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "pr_number" {
  description = "Pull request number"
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

variable "anthropic_api_key" {
  description = "Anthropic API key"
  type        = string
  sensitive   = true
}

variable "gmail_client_id" {
  description = "Gmail OAuth client ID"
  type        = string
  sensitive   = true
}

variable "gmail_client_secret" {
  description = "Gmail OAuth client secret"
  type        = string
  sensitive   = true
}

variable "gmail_refresh_token" {
  description = "Gmail OAuth refresh token"
  type        = string
  sensitive   = true
}

variable "max_emails_per_run" {
  description = "Maximum emails to process per Lambda invocation"
  type        = number
  default     = 3
}
