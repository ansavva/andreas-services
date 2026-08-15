variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "media_bucket_name" {
  description = <<-EOT
    The x-harness media bucket studio reads. Owned by the x-harness pipeline and
    referenced by name only — studio's Terraform never manages it, and the API's
    IAM policy grants read actions exclusively.
  EOT
  type        = string
  default     = "xharness-prod-media-us-east-1"
}

variable "media_root_prefix" {
  description = "The single prefix inside the media bucket studio may browse"
  type        = string
  default     = "media/"
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
