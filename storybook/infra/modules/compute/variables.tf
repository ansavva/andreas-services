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

variable "image_queue_arn" {
  description = "SQS queue ARN for image normalization jobs"
  type        = string
}

variable "cors_allowed_origins" {
  description = "CORS allowed origins"
  type        = list(string)
}

variable "dynamodb_table_arns" {
  description = "Map of DynamoDB table ARNs the Lambda needs access to"
  type        = map(string)
  default     = {}
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
