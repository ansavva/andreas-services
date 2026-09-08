variable "bucket_name" {
  description = "Globally unique name for the lesson content bucket"
  type        = string
}

variable "upload_origins" {
  description = "Origins allowed to PUT with a presigned URL — the app's own hosts, never '*'"
  type        = list(string)
}

variable "cloudfront_distribution_arn" {
  description = "ARN of the distribution permitted to read objects, via origin access control. Unused when serve_via_cloudfront is false."
  type        = string
  default     = ""
}

variable "serve_via_cloudfront" {
  description = <<-EOT
    Whether to attach the bucket policy granting CloudFront read.

    **A separate flag rather than `cloudfront_distribution_arn != ""`, and the
    difference is not cosmetic.** The ARN is a resource attribute, so once the
    caller adds a `depends_on` it is unknown at plan time — and a `count` that
    depends on it fails the whole plan with "Invalid count argument". That is a
    plan-time error `terraform validate` cannot see, so it surfaces in a deploy.

    This is a literal at every call site, so the count is always known.
  EOT
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
