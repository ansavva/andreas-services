variable "project" {
  description = "Project name; the first segment of every resource name"
  type        = string
}

variable "environment" {
  description = "Deployment environment; the second segment of every resource name"
  type        = string
}

variable "create_ecr" {
  description = "Whether this env owns the ECR repositories"
  type        = bool
  default     = true
}

variable "api_image_uri" {
  description = "Override image for the API Lambda when create_ecr = false"
  type        = string
  default     = ""
}

variable "www_image_uri" {
  description = "Override image for the www Lambda when create_ecr = false"
  type        = string
  default     = ""
}

variable "intake_table_arn" {
  description = "ARN of the intake DynamoDB table the API Lambda may access"
  type        = string
}

variable "intake_table_name" {
  description = "Name of the intake DynamoDB table, passed to the API Lambda"
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
