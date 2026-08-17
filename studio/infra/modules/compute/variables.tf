variable "project" {
  description = "Project name; the first segment of every resource name"
  type        = string
}

variable "environment" {
  description = "Deployment environment; the second segment of every resource name"
  type        = string
}

variable "create_ecr" {
  description = "Whether this env owns the ECR repository"
  type        = bool
  default     = true
}

variable "api_image_uri" {
  description = "Override image for the API Lambda when create_ecr = false"
  type        = string
  default     = ""
}

variable "media_bucket_name" {
  description = <<-EOT
    Name of the media bucket the API reads and writes. Pass `modules/media`'s
    output rather than a literal: this module still declares no bucket resource
    of its own — it only writes the IAM policy — and taking the name from the
    module is what orders the two correctly.
  EOT
  type        = string
}

variable "media_root_prefix" {
  description = <<-EOT
    The prefix inside the bucket the API may reach. Empty means the whole bucket,
    which is what prod uses now that the pipeline writes `characters/`,
    `projects/` and `phrasebook/` at the top level instead of wrapping them in
    `media/`. Any other value must end in a slash.
  EOT
  type        = string

  validation {
    condition     = var.media_root_prefix == "" || endswith(var.media_root_prefix, "/")
    error_message = "media_root_prefix must be empty (the whole bucket) or end in a slash, or the IAM prefix conditions match too much."
  }
}

variable "allowed_origin" {
  description = "Origin allowed by the API's CORS policy (the app's own origin)"
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
