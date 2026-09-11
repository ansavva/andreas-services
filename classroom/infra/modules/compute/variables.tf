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

variable "lessons_bucket_name" {
  description = "Bucket holding every lesson's uploaded files; the API signs uploads into it"
  type        = string
}

variable "lessons_bucket_arn" {
  description = "ARN of the lesson bucket, scoping the API's S3 grant"
  type        = string
}

variable "allowed_origin" {
  description = "Origin the browser API accepts — the admin app's host. Never \"*\": lessons run untrusted scripts."
  type        = string
}

variable "cognito_user_pool_id" {
  description = "Pool whose ID tokens the API accepts; also the JWKS issuer"
  type        = string
}

variable "cognito_client_id" {
  description = "App client a token's `aud` must match"
  type        = string
}
