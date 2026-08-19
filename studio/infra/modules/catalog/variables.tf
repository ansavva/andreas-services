variable "table_name" {
  description = <<-EOT
    Name of the catalog table, composed by the environment rather than built from
    a literal here — `[project]-[env]-[component]`, so `studio-prod-catalog`.

    Changing this on a live table is a destroy-and-recreate that takes every row
    with it, and the rows ARE the library: the bytes in the media bucket survive
    but nothing can name, place or reach them again.
  EOT
  type        = string
}

variable "point_in_time_recovery_enabled" {
  description = <<-EOT
    Continuous backups for the table — 35 days, restorable to any second.

    Defaults to ON. This is the only recovery the catalog has; see the reasoning
    at the `point_in_time_recovery` block in main.tf.
  EOT
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
