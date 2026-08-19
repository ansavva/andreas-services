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
