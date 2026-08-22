variable "bucket_name" {
  description = "Globally unique S3 bucket name, e.g. studio-dev-seed-us-east-1"
  type        = string
}

variable "tags" {
  description = "Tags applied to the bucket"
  type        = map(string)
  default     = {}
}
