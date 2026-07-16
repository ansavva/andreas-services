variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "domain_name" {
  type = string
}

variable "route53_zone_id" {
  type = string
}

variable "humbugg_role_name" {
  type = string
}

variable "humbugg_sender_address" {
  type = string
}

variable "tags" {
  type = map(string)
}
