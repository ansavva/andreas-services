variable "project" {
  description = "Project name"
  type        = string
}

variable "domain_name" {
  description = "Domain name for the application"
  type        = string
}

variable "certificate_arn" {
  description = "ARN of the validated us-east-1 certificate used as the CloudFront viewer certificate"
  type        = string
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID"
  type        = string
}

variable "marketing_bucket_id" {
  description = "Frontend S3 bucket ID"
  type        = string
}

variable "marketing_bucket_arn" {
  description = "Frontend S3 bucket ARN"
  type        = string
}

variable "marketing_bucket_regional_domain_name" {
  description = "Frontend S3 bucket regional domain name"
  type        = string
}

variable "marketing_api_domain" {
  description = "Marketing SSR HTTP API host without a scheme"
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}

variable "environment" {
  description = "Deployment environment; the second segment of every resource name"
  type        = string
}
