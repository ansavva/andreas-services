# modules/image_worker/variables.tf

variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "s3_bucket_arn" {
  description = "S3 bucket ARN for backend files"
  type        = string
}

variable "queue_arn" {
  description = "SQS queue ARN for image normalization jobs"
  type        = string
}

variable "enable_vpc" {
  description = "Attach the worker Lambda to a VPC"
  type        = bool
  default     = false
}

variable "vpc_id" {
  description = "VPC ID for the worker Lambda"
  type        = string
  default     = null
}

variable "subnet_ids" {
  description = "Subnet IDs for the worker Lambda"
  type        = list(string)
  default     = []
}

variable "environment_variables" {
  description = "Optional Lambda environment variables"
  type        = map(string)
  default     = {}
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
