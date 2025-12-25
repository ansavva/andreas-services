# modules/database/variables.tf

variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment (production, staging, etc.)"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID where DocumentDB will be deployed"
  type        = string
}

variable "subnet_ids" {
  description = "List of subnet IDs for DocumentDB subnet group"
  type        = list(string)
}

variable "lambda_security_group_ids" {
  description = "Security group IDs of Lambda functions that need access"
  type        = list(string)
  default     = []
}

variable "master_username" {
  description = "Master username for DocumentDB"
  type        = string
  default     = "docdbadmin"
}

variable "master_password" {
  description = "Master password for DocumentDB"
  type        = string
  sensitive   = true
}

variable "instance_class" {
  description = "Instance class for DocumentDB instances"
  type        = string
  default     = "db.t3.medium"
}

variable "instance_count" {
  description = "Number of DocumentDB instances"
  type        = number
  default     = 1
}

variable "backup_retention_days" {
  description = "Number of days to retain backups"
  type        = number
  default     = 7
}

variable "skip_final_snapshot" {
  description = "Skip final snapshot on deletion (dev/test only)"
  type        = bool
  default     = false
}

variable "kms_key_id" {
  description = "KMS key ID for encryption (optional)"
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
