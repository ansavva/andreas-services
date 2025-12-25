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

variable "docdb_master_username" {
  description = "Master username for shared DocumentDB cluster"
  type        = string
  default     = "docdbadmin"
}

variable "docdb_master_password" {
  description = "Master password for shared DocumentDB cluster"
  type        = string
  sensitive   = true
}
