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

variable "deletion_protection_enabled" {
  description = <<-EOT
    Refuse `DeleteTable` at the AWS API, not just in Terraform.

    Defaults to ON, and it is not a duplicate of `prevent_destroy` on the media
    bucket. That is a Terraform lifecycle guard: it errors at plan time, so a
    `terraform destroy` over this whole state fails and removes nothing. It says
    nothing about a `-target`ed destroy of this table alone, a console click, or
    a stray CLI call — and studio's pipeline half runs under a human's own AWS
    login with real credentials, so those are the paths that matter here.

    It is also the half PITR does not cover. PITR pays to *recover*, out of
    band, into a new table, by someone who first has to notice. This makes the
    delete fail instead, at the moment a person can still change their mind.

    Turning it off is an in-place update, so a genuine teardown is a deliberate
    two-step rather than a blocked one.
  EOT
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
