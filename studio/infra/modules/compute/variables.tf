variable "project" {
  description = "Project name; the first segment of every resource name"
  type        = string
}

variable "environment" {
  description = "Deployment environment; the second segment of every resource name"
  type        = string
}

variable "create_ecr" {
  description = "Whether this env owns the ECR repository"
  type        = bool
  default     = true
}

variable "api_image_uri" {
  description = "Override image for the API Lambda when create_ecr = false"
  type        = string
  default     = ""
}

variable "media_bucket_name" {
  description = <<-EOT
    Name of the media bucket the API reads and writes. Pass `modules/media`'s
    output rather than a literal: this module still declares no bucket resource
    of its own — it only writes the IAM policy — and taking the name from the
    module is what orders the two correctly.
  EOT
  type        = string
}

variable "media_root_prefix" {
  description = <<-EOT
    The prefix inside the bucket the API may reach. Empty means the whole bucket,
    which is what prod uses now that the pipeline writes `characters/`,
    `projects/` and `phrasebook/` at the top level instead of wrapping them in
    `media/`. Any other value must end in a slash.
  EOT
  type        = string

  validation {
    condition     = var.media_root_prefix == "" || endswith(var.media_root_prefix, "/")
    error_message = "media_root_prefix must be empty (the whole bucket) or end in a slash, or the IAM prefix conditions match too much."
  }
}

variable "allowed_origin" {
  description = "Origin allowed by the API's CORS policy (the app's own origin)"
  type        = string
}

variable "catalog_table_name" {
  description = <<-EOT
    Name of the catalog table, reaching the Lambda as `STUDIO_CATALOG_TABLE`.
    Pass `modules/catalog`'s output rather than a literal, for the same reason
    `media_bucket_name` does: this module declares no table of its own, and
    taking the name from the module is what orders the two.

    A name here that no longer matches the table is not a plan-time error — it
    is a runtime `ResourceNotFoundException` on the first query.
  EOT
  type        = string
}

variable "catalog_table_arn" {
  description = <<-EOT
    ARN of the catalog table, used to scope the API role's item grants. Take it
    from `modules/catalog`'s output rather than rebuilding it from the name:
    that is what gives the policy a real dependency edge on the table it grants
    access to.

    The policy appends `/index/*` to it — a Query against a GSI is authorized
    against the index, not the table.
  EOT
  type        = string
}

variable "cognito_user_pool_id" {
  description = <<-EOT
    The pool the API validates tokens against, reaching the Lambda as
    `STUDIO_COGNITO_USER_POOL_ID`. It builds the issuer and the JWKS URL. The
    Lambda validates in-app rather than trusting the gateway's authorizer,
    because the authorizer's claims cannot reach Flask through Mangum — see the
    `environment` block in main.tf.
  EOT
  type        = string
}

variable "cognito_client_id" {
  description = <<-EOT
    The app client the SPA signs in against, reaching the Lambda as
    `STUDIO_COGNITO_CLIENT_ID`. Checked against the token's `aud`: without it a
    token minted for any other client of the same pool would validate.
  EOT
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}

variable "replicate_token_parameter" {
  description = <<-EOT
    Name of the SSM SecureString holding the Replicate API token, reaching the
    Lambda as `STUDIO_REPLICATE_TOKEN_PARAMETER`. A NAME and never a value: the
    API reads it at call time so the secret never sits in the function's
    environment. Empty in an environment that has none — a developer's machine
    supplies `REPLICATE_API_TOKEN` directly and never touches SSM.
  EOT
  type        = string
  default     = ""
}

variable "replicate_token_parameter_arn" {
  description = <<-EOT
    ARN of the same parameter, scoping the `ssm:GetParameter` grant to exactly
    one name. Empty means no grant is written at all, which is what an
    environment with no deployed API wants.
  EOT
  type        = string
  default     = ""
}
