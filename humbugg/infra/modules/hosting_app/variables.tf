variable "project" {
  description = "Project name"
  type        = string
}

variable "domain_name" {
  description = "Apex domain; the app is served at app.<domain_name>"
  type        = string
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID for the apex domain"
  type        = string
}

variable "certificate_arn" {
  description = "Validated us-east-1 ACM certificate ARN covering app.<domain_name>"
  type        = string
}

variable "app_web_bucket_id" {
  description = "Expo web export S3 bucket ID"
  type        = string
}

variable "app_web_bucket_arn" {
  description = "Expo web export S3 bucket ARN"
  type        = string
}

variable "app_web_bucket_regional_domain_name" {
  description = "Expo web export S3 bucket regional domain name"
  type        = string
}

variable "avatars_bucket_id" {
  description = "Shared application S3 bucket ID; only its avatars/ prefix is served"
  type        = string
}

variable "avatars_bucket_arn" {
  description = "Shared application S3 bucket ARN"
  type        = string
}

variable "avatars_bucket_regional_domain_name" {
  description = "Shared application S3 bucket regional domain name"
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
