variable "project" {
  description = "Project name, first segment of every resource name"
  type        = string
}

variable "environment" {
  description = "Deployment environment, second segment of every resource name (prod/dev)"
  type        = string
}

variable "core_table_name" {
  description = "Name of the scout-prod-core DynamoDB table"
  type        = string
}

variable "settings_table_name" {
  description = "Name of the scout-prod-settings DynamoDB table"
  type        = string
}

variable "events_api_image_uri" {
  description = "ECR image URI for the events API Lambda (required when create_ecr = false)"
  type        = string
  default     = ""
}

variable "renderer_image_uri" {
  description = "ECR image URI for the headless renderer Lambda (required when create_ecr = false)"
  type        = string
  default     = ""
}

variable "processor_env_vars" {
  description = "Environment variables for the source-run processor Lambda (e.g. ANTHROPIC_API_KEY)"
  type        = map(string)
  sensitive   = true
  default     = {}
}

variable "artifacts_bucket" {
  description = "S3 bucket for source-run artifacts (root bodies, linked pages, transcripts)"
  type        = string
  default     = ""
}

variable "images_bucket" {
  description = "S3 bucket for event images"
  type        = string
  default     = ""
}

variable "create_ecr" {
  description = "Whether to create ECR repositories (false for PR environments)"
  type        = bool
  default     = true
}

variable "create_eventbridge" {
  description = "Whether to create the EventBridge schedule rule (false for PR environments)"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
