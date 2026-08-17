variable "bucket_name" {
  description = <<-EOT
    Globally-unique S3 bucket name for the media library.

    The live value, `xharness-prod-media-us-east-1`, predates studio absorbing
    the generation pipeline and does not follow the repo's
    `[project]-[env]-[component]-[region]` convention. It is grandfathered
    deliberately: renaming a bucket is a destroy-and-recreate, and this one holds
    ~700 MB that would have to be copied and re-pointed from the skills, the API
    and the deploy workflow in one move. A later pass does that properly.
  EOT
  type        = string
}

variable "versioning_enabled" {
  description = "Keep prior revisions of same-named objects, so an overwrite or a delete is recoverable."
  type        = bool
  default     = true
}

variable "key_prefix" {
  description = <<-EOT
    Optional key prefix the whole tree lives under. EMPTY by default: the tree is
    at the bucket root, because the bucket IS the media store. (There was a
    `media/` wrapper once, left over from mirroring a Google Drive folder 1:1; it
    bought nothing and was removed.) This stays as the single seam for staging a
    second copy of the tree in the same bucket. Include the trailing slash.
  EOT
  type        = string
  default     = ""

  validation {
    condition     = var.key_prefix == "" || endswith(var.key_prefix, "/")
    error_message = "key_prefix must be empty or end with a trailing slash (e.g. \"staging/\")."
  }
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
