variable "aws_region" {
  description = "AWS region where SES sends Humbugg mail"
  type        = string
}

variable "domain_name" {
  description = "Verified SES identity domain"
  type        = string
}

variable "route53_zone_id" {
  description = "Route53 hosted zone containing the SES identity records"
  type        = string
}
