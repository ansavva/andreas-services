variable "media_bucket_name" {
  description = <<-EOT
    Globally-unique name for this machine's development media bucket, composed
    by the environment rather than built from a literal here —
    `studio-dev-<machine_short_id>-media-<region>`.

    Unlike the prod bucket, changing this is safe: a destroy-and-recreate loses
    only seed data, and `force_destroy` means the destroy half actually
    succeeds.
  EOT
  type        = string
}

variable "catalog_table_name" {
  description = <<-EOT
    Name of this machine's development catalog table, composed by the
    environment — `studio-dev-<machine_short_id>-catalog`.

    Same schema as the prod table (`modules/catalog`), so the same code paths
    run against it. Same caveat as the bucket: replacing it costs only
    fixtures.
  EOT
  type        = string
}

variable "tags" {
  description = <<-EOT
    Tags applied to every development resource. Must carry `DeveloperMachineId`,
    `DeveloperPrincipal` and `MachineName` — a stray per-machine bucket or table
    in the shared account is traced back to a person through these and nothing
    else.
  EOT
  type        = map(string)
  default     = {}
}

variable "cors_allowed_origins" {
  description = <<-EOT
    Origins allowed to send the presigned upload PUT — the local SPA's, which is
    Vite on `http://localhost:5173`. Same shape and same reasoning as
    `modules/media`'s; see the resource comment there.

    A list rather than a string because the module argument in `modules/media`
    is one, and the two rules are meant to be diffable against each other.
  EOT
  type        = list(string)
  default     = ["http://localhost:5173"]

  validation {
    condition     = !contains(var.cors_allowed_origins, "*")
    error_message = "A wildcard origin would let any page complete an upload PUT. Name the SPA's origin."
  }
}
