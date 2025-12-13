variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "domain_name" {
  description = "Root domain name"
  type        = string
  default     = "andreas.services"
}

variable "app_subdomain" {
  description = "Subdomain for the application"
  type        = string
  default     = "storybook.andreas.services"
}

variable "frontend_path" {
  description = "Path prefix for frontend"
  type        = string
  default     = "/app"
}

variable "backend_path" {
  description = "Path prefix for backend API"
  type        = string
  default     = "/api"
}

variable "replicate_api_token" {
  description = "Replicate API token"
  type        = string
  sensitive   = true
}
