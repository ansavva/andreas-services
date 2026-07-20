variable "resource_prefix" {
  description = "Unique per-machine prefix for development DynamoDB tables"
  type        = string
}

variable "app_bucket_name" {
  description = "Globally unique per-machine development application bucket name"
  type        = string
}

variable "tags" {
  description = "Tags applied to every development resource"
  type        = map(string)
  default     = {}
}
