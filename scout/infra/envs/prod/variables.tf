variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "anthropic_api_key" {
  description = "Anthropic API key for email processor"
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
