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

variable "google_dkim_txt_value" {
  description = "DKIM TXT value (v=DKIM1; k=rsa; p=...) generated in Google Admin for the domain; the record is only created when non-empty"
  type        = string
  default     = ""
}

variable "apex_txt_additional_records" {
  description = "Extra apex TXT strings (e.g. google-site-verification=...) merged into the single apex TXT record set alongside SPF"
  type        = list(string)
  default     = []
}
