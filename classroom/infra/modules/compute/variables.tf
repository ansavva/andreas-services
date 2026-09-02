variable "project" {
  description = "Project name, first segment of every resource name"
  type        = string
}

variable "environment" {
  description = "Deployment environment, second segment of every resource name (prod/dev)"
  type        = string
}

variable "create_ecr" {
  description = "Create the ECR repository for the API image"
  type        = bool
  default     = true
}

variable "api_image_uri" {
  description = "Image URI to use when create_ecr is false"
  type        = string
  default     = ""
}

variable "pages_table_name" {
  description = "Name of the pages DynamoDB table"
  type        = string
}

variable "pages_table_arn" {
  description = "ARN of the pages DynamoDB table"
  type        = string
}

variable "public_site_url" {
  description = "Absolute public base URL of the site, used to build share links"
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
