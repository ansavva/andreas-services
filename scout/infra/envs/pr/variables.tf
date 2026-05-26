variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "pr_number" {
  description = "Pull request number"
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
