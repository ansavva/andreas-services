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

    It did not always. See `media_archive_bucket_name` below for the bucket this
    one replaced and why that one is still here.
  EOT
  type        = string
  default     = "studio-prod-media-us-east-1"
}

variable "media_archive_bucket_name" {
  description = <<-EOT
    The ORIGINAL media bucket, kept permanently.

    Created from a separate `xharness` repo before studio absorbed the pipeline,
    which is why its name does not follow the convention. It was not renamed,
    because an S3 bucket cannot be: a name change is a destroy-and-recreate.
    `media_bucket_name` is a second bucket, and the current objects were copied
    across.

    A copy of current objects is not a copy of the bucket. This one holds 1,613
    noncurrent versions and 718 keys that survive only behind a delete marker —
    the entire "an overwrite or a delete is recoverable" property the versioning
    on these buckets exists for. That history is not reproducible anywhere else,
    so the archive is retained rather than emptied and dropped. It carries
    `prevent_destroy` for the same reason the live bucket does.
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
