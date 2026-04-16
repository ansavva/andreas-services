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
