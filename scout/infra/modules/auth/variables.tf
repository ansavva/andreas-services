variable "pr_number" {
  description = "PR number for naming this ephemeral Cognito pool"
  type        = string
}

variable "frontend_base_url" {
  description = "Base URL of the PR preview frontend (e.g. https://scout-pr.andreas.services)"
  type        = string
  default     = "https://scout-pr.andreas.services"
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
