# envs/prod/variables.tf

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "replicate_api_token" {
  description = "Replicate API token for AI features"
  type        = string
  sensitive   = true
}
