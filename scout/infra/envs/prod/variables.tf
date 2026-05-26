variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "anthropic_api_key" {
  description = "Anthropic API key for the source-run processor (Agent SDK)"
  type        = string
  sensitive   = true
}
