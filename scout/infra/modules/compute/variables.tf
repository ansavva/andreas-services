variable "pr_number" {
  description = "PR number (empty string for non-PR environments)"
  type        = string
  default     = ""
}

variable "table_suffix" {
  description = "Suffix for all DynamoDB table names (empty for prod, '-pr-N' for previews)"
  type        = string
  default     = ""
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
