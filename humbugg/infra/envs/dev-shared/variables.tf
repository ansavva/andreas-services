variable "aws_region" {
  description = "AWS region for the shared development resources"
  type        = string
  default     = "us-east-1"
}

variable "aws_principal_arn" {
  description = "Caller ARN of whoever last applied, recorded as a tag"
  type        = string
}
