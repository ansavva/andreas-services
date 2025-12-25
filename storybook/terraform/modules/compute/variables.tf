# modules/compute/variables.tf

variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  type        = string
}

variable "cognito_client_id" {
  description = "Cognito Client ID"
  type        = string
}

variable "s3_bucket_id" {
  description = "S3 bucket ID for backend files"
  type        = string
}

variable "s3_bucket_arn" {
  description = "S3 bucket ARN for backend files"
  type        = string
}

variable "cors_allowed_origins" {
  description = "CORS allowed origins"
  type        = list(string)
}

variable "additional_env_vars" {
  description = "Additional environment variables for Lambda"
  type        = map(string)
  default     = {}
}

variable "enable_vpc" {
  description = "Whether to place the Lambda inside a VPC"
  type        = bool
  default     = false
}

variable "vpc_id" {
  description = "VPC ID for Lambda (required if enable_vpc = true)"
  type        = string
  default     = null
}

variable "subnet_ids" {
  description = "Subnet IDs for Lambda (required if enable_vpc = true)"
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
