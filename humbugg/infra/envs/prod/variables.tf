variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "support_forward_to" {
  description = <<-EOT
    Private destination inbox for forwarded support@humbugg.com mail. This is a
    human-provided secret: leave empty in committed config and inject via
    TF_VAR_support_forward_to in CI (sourced from the SUPPORT_FORWARD_TO GitHub
    environment secret). Never commit the real address.
  EOT
  type        = string
  default     = ""
  sensitive   = true
}
