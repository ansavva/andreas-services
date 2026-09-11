variable "bucket_name" {
  description = "S3 bucket name"
  type        = string
}

variable "force_destroy" {
  description = "Allow the bucket to be destroyed even if it still contains objects."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
