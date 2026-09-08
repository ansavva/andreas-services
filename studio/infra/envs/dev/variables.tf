# Every variable here is supplied by `scripts/dev-aws-common.sh` at apply time
# (`set_terraform_vars`), not by a committed tfvars file. The validations are
# the same ones humbugg's dev environment uses: they are what stops a malformed
# machine id from becoming a resource name nothing can find again.

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

variable "spa_ports" {
  description = <<-EOT
    The localhost ports the SPA may be served from — every one of them is a
    registered Cognito callback and an allowed origin on the media bucket's
    CORS rule, so `dev-up.sh` can take the first free one instead of the one
    pinned in `frontend/vite.config.ts`. Another project's dev server on
    `:5173` used to mean studio could not sign in at all: Vite hopped to
    `:5175` on its own, and Cognito refused the callback.

    Four rather than one because a redirect URI has to be known to the pool in
    advance, and re-applying this stack to change ports is the wrong price for
    a port clash. Order matters: it is the order `dev-up.sh` tries them in.
    The three fallbacks sit past every other service's dev port — the root
    CLAUDE.md's table — so studio never falls onto classroom's or website's.

    It has a default for the reason `spa_origins` did before it: every other
    variable in this file identifies the machine and must not be guessable,
    this one is the same everywhere.
  EOT
  type        = list(number)
  default     = [5173, 5178, 5179, 5180]

  validation {
    condition     = length(var.spa_ports) > 0 && alltrue([for p in var.spa_ports : p > 1024 && p < 65536])
    error_message = "spa_ports must name at least one unprivileged port."
  }
}
