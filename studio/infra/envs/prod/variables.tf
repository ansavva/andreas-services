variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "media_bucket_name" {
  description = <<-EOT
    The media bucket. Created by `modules/media` in this state, read by the API
    and written by the generation skills. The name is grandfathered from before
    studio absorbed the pipeline and does not follow the naming convention —
    `modules/media/variables.tf` explains why it has not been changed yet.
  EOT
  type        = string
  default     = "xharness-prod-media-us-east-1"
}

variable "media_root_prefix" {
  description = <<-EOT
    The prefix inside the media bucket everything lives under. Empty is the whole
    bucket, and that is the default: the pipeline used to wrap its output in
    `media/` and now writes `characters/`, `projects/` and `phrasebook/` at the
    top level. Set a slash-terminated value to narrow the API, the Lambda's IAM
    policy and the bucket module together onto one subtree.
  EOT
  type        = string
  default     = ""
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
