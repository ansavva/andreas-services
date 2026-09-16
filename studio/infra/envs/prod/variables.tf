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

variable "invite_code" {
  description = <<-EOT
    The invite code a sign-up must present. Passed to `modules/auth`, where an
    empty value — the default — makes the pre-sign-up trigger refuse every
    sign-up. In CI this is `TF_VAR_invite_code`, from the `STUDIO_INVITE_CODE`
    secret on the studio-production environment; never a tfvars file.
  EOT
  type        = string
  default     = ""
  sensitive   = true
}
