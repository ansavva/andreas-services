variable "table_suffix" {
  description = "Per-environment suffix for table names (e.g. \"\" for prod)"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
