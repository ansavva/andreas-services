variable "table_suffix" {
  description = "Per-environment table suffix (e.g. \"\" for prod)"
  type        = string
  default     = ""
}

variable "pr_number" {
  description = "PR number for ephemeral previews; \"\" for prod"
  type        = string
  default     = ""
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

variable "frontend_image_uri" {
  description = "Override image for the frontend Lambda when create_ecr = false"
  type        = string
  default     = ""
}

variable "intake_table_arn" {
  description = "ARN of the intake DynamoDB table the API Lambda may access"
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
