variable "project" {
  description = "Service/project name (e.g. humbugg)"
  type        = string
}

variable "environment" {
  description = "Environment name (e.g. production)"
  type        = string
}

variable "aws_region" {
  description = "AWS region where SES receives inbound mail"
  type        = string
}

variable "domain_name" {
  description = "Mail domain that receives support mail (e.g. humbugg.com)"
  type        = string
}

variable "route53_zone_id" {
  description = "Route53 hosted zone for the mail domain (data-sourced; not owned here)"
  type        = string
}

variable "support_recipient" {
  description = "The public support address that mail is accepted for"
  type        = string
  default     = "support@humbugg.com"
}

variable "from_address" {
  description = "Verified SES sender used for the forwarded message"
  type        = string
}

variable "ses_identity_arn" {
  description = "ARN of the verified SES domain identity used to send the forward"
  type        = string
}

variable "support_forward_to" {
  description = <<-EOT
    Private destination inbox for forwarded support mail. This is a human-provided
    secret; leave empty in committed config and inject via TF_VAR_support_forward_to
    (sourced from the SUPPORT_FORWARD_TO GitHub environment secret). Stored as an
    SSM SecureString; the Lambda reads it at runtime.
  EOT
  type        = string
  default     = ""
  sensitive   = true
}

variable "inbound_object_expiration_days" {
  description = "Days after which raw inbound messages are expired from S3"
  type        = number
  default     = 30
}

variable "max_message_bytes" {
  description = "Maximum assembled forward size before attachments are dropped"
  type        = number
  default     = 9000000
}

variable "max_attachment_bytes" {
  description = "Maximum per-attachment size that is forwarded"
  type        = number
  default     = 6000000
}

variable "lambda_source_dir" {
  description = "Path to the Python Lambda source root (contains the support_forwarder package)"
  type        = string
}

variable "tags" {
  description = "Common resource tags"
  type        = map(string)
  default     = {}
}
