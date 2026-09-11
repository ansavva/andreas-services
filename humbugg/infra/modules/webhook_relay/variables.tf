variable "name_prefix" {
  description = <<-EOT
    Everything here is named `<prefix>-stripe-webhook…`. Prod passes
    `humbugg-prod`; dev passes `humbugg-dev-<short12>`, the machine id inside
    the environment segment, because two developers share one AWS account and
    one Stripe sandbox. A prefix rather than a project/environment pair so this
    module has no opinion about what an environment is called.
  EOT
  type        = string
}

variable "create_consumer" {
  description = <<-EOT
    Whether this environment gets a queue consumer Lambda. **A literal, never
    derived from another resource**: it drives a `count`, and a `count` that
    depends on a resource attribute cannot be resolved at plan time — the
    `Invalid count argument` that failed a prod deploy in studio.

    `false` is what the per-machine dev environment passes: it has no ECR
    repository, and its consumer is the same image as a Compose service beside
    the API. Prod passes `true` and the three `consumer_*` values below.
  EOT
  type        = bool
  default     = false
}

variable "consumer_image_uri" {
  description = <<-EOT
    The API's container image, which the consumer runs entered through
    `ConsumerHost` rather than the HTTP API. `<ecr repo>:latest`, as every
    Lambda in `modules/compute` is declared; the deploy workflow pins the real
    `:sha`. Required with `create_consumer`.
  EOT
  type        = string
  default     = ""
}

variable "consumer_role_arn" {
  description = <<-EOT
    Execution role for the consumer. Pass the API Lambda's: the work is the
    API's — Stripe settings, the billing and groups tables — and a second role
    would be a hand-maintained copy of the policies in `modules/compute` that
    drifts. Required with `create_consumer`.
  EOT
  type        = string
  default     = ""
}

variable "consumer_role_name" {
  description = "Name of the same role, so the queue grant can be attached to it as an inline policy."
  type        = string
  default     = ""
}

variable "alarm_topic_arn" {
  description = "SNS topic the dead-letter alarm publishes to. Empty means no alarm is created, which is what dev passes."
  type        = string
  default     = ""
}

variable "throttle_rate" {
  description = "Steady-state requests per second the public endpoint accepts."
  type        = number
  default     = 20
}

variable "throttle_burst" {
  description = "Burst above the steady rate the public endpoint accepts."
  type        = number
  default     = 40
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
