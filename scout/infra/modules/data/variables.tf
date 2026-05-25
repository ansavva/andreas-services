variable "table_suffix" {
  description = "Suffix for DynamoDB table names (empty for prod, '-pr-N' for previews)"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
