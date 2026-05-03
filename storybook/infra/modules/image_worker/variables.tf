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
