variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "media_bucket_name" {
  description = <<-EOT
    The media bucket. Created by `modules/media` in this state, read by the API
    and written by the generation skills. Follows the repo's
    `[project]-[env]-[component]-[region]` convention.

    Do not change this value to rename the bucket. S3 has no rename: a changed
    name is a destroy-and-recreate, and this bucket holds the only copy of the
    generated media. Renaming means a second bucket and a verified copy, which
    is what was done in August 2026 — see `../../README.md`.
  EOT
  type        = string
  default     = "studio-prod-media-us-east-1"
}

variable "api_throttling_rate_limit" {
  description = "Steady-state request rate limit on the API stage"
  type        = number
  default     = 25
}

variable "api_throttling_burst_limit" {
  description = "Burst request limit on the API stage"
  type        = number
  default     = 50
}
