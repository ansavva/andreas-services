# Every variable here is supplied by `scripts/dev-aws-common.sh` at apply time
# (`set_terraform_vars`), not by a committed tfvars file. The validations are
# what stop a malformed machine id from becoming a resource name nothing can
# find again.

variable "aws_region" {
  description = "AWS region for this machine's development resources"
  type        = string
  default     = "us-east-1"
}

variable "aws_account_id" {
  description = "AWS account that owns this machine's development resources"
  type        = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be a 12-digit AWS account ID."
  }
}

variable "aws_principal_arn" {
  description = "Caller ARN recorded as the development resource owner"
  type        = string
}

variable "machine_id" {
  description = "Persistent UUID generated for this OS user on this machine"
  type        = string
  validation {
    condition     = can(regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", var.machine_id))
    error_message = "machine_id must be a lowercase UUID."
  }
}

variable "machine_short_id" {
  description = "First 12 hexadecimal characters of machine_id, used in resource names"
  type        = string
  validation {
    condition     = can(regex("^[0-9a-f]{12}$", var.machine_short_id))
    error_message = "machine_short_id must contain exactly 12 lowercase hexadecimal characters."
  }
}

variable "machine_name" {
  description = "Human-readable machine hostname stored only as a resource tag"
  type        = string
}

variable "spa_origin" {
  description = <<-EOT
    Where the local SPA is served from. It is the origin half of the exact
    callback and logout URLs registered on the app client, so it has to agree
    with Vite's port character for character — that port is pinned in
    `frontend/vite.config.ts`, and `dev-up.sh` prints the same URL, so the
    default is right on every machine and `dev-aws-common.sh` does not pass it.

    It has a default for that reason, unlike every other variable here: those
    identify the machine and must not be guessable, this one is the same
    everywhere.
  EOT
  type        = string
  default     = "http://localhost:5174"
}
