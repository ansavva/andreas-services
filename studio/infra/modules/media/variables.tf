variable "bucket_name" {
  description = <<-EOT
    Globally-unique S3 bucket name for the media library.

    Do not change this on an existing instance. A changed bucket name is a
    destroy-and-recreate, and this bucket holds the only copy of the generated
    media. The August 2026 rename was done as a second module instance plus a
    verified copy, then a deliberate deletion of the old bucket — not by
    editing this value.
  EOT
  type        = string
}

variable "versioning_enabled" {
  description = "Keep prior revisions of same-named objects, so an overwrite or a delete is recoverable."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}

variable "cors_allowed_origins" {
  description = <<-EOT
    Origins allowed to send the presigned PUT that uploads a file. The SPA's
    origin and nothing else — this is not the API's CORS list and does not need
    to hold the API's own hostname, because the bytes go browser → S3 directly
    and never through the API.

    The default is prod's SPA. It is a default rather than a required argument
    so a `terraform validate` or a scratch instance of this module does not have
    to invent one, and it is still passed explicitly from `envs/prod` so the
    origin is visible next to the domain it is built from.
  EOT
  type        = list(string)
  default     = ["https://studio.andreas.services"]

  validation {
    condition     = !contains(var.cors_allowed_origins, "*")
    error_message = "A wildcard origin would let any page complete an upload PUT. Name the SPA's origin."
  }
}

variable "noncurrent_version_expiration_days" {
  description = "Days a superseded object version is kept before it expires. The recovery window for a delete or an overwrite."
  type        = number
  default     = 30
}
