variable "name" {
  description = "Base name for the Cognito user pool"
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
