variable "bucket_name" {
  description = <<-EOT
    Globally-unique S3 bucket name for the media library.

    This module is instantiated TWICE in `envs/prod`: once for the live bucket
    (`studio-prod-media-us-east-1`) and once for the archive it replaced
    (`xharness-prod-media-us-east-1`, named before studio absorbed the
    generation pipeline). Both get identical treatment — versioned, private,
    encrypted, `prevent_destroy` — because the archive holds the version history
    the live bucket's copy does not carry, and is not disposable.

    Do not "fix" this by changing the name on an existing instance. A changed
    bucket name is a destroy-and-recreate, which for either of these is data
    loss; the second bucket exists precisely because that is not a survivable
    operation.
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
