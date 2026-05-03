# modules/storage/variables.tf

variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "cors_allowed_origins" {
  description = "List of allowed origins for CORS"
  type        = list(string)
}

variable "create_frontend_bucket" {
  description = "Whether to create frontend S3 bucket"
  type        = bool
  default     = false
}

variable "frontend_bucket_name" {
  description = "S3 bucket name for frontend (overrides the default project-frontend-environment pattern)"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
