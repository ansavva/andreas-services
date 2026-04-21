# envs/shared/variables.tf

variable "aws_region" {
  description = "AWS region for shared infrastructure"
  type        = string
  default     = "us-east-1"
}

variable "domain_name" {
  description = "Root domain name"
  type        = string
  default     = "andreas.services"
}

variable "github_repo" {
  description = "GitHub repo allowed to assume the Actions role (owner/repo)"
  type        = string
  default     = "ansavva/andreas-services"
}
