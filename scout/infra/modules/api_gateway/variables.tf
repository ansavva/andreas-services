variable "pr_number" {
  description = "PR number for naming (empty for prod)"
  type        = string
  default     = ""
}

variable "lambda_invoke_arn" {
  description = "Lambda invoke ARN for API Gateway integration"
  type        = string
}

variable "lambda_function_name" {
  description = "Lambda function name for permission resource"
  type        = string
}

variable "stage_name" {
  description = "API Gateway stage name"
  type        = string
  default     = "prod"
}

variable "throttle_rate" {
  description = "API Gateway throttle rate limit (requests per second)"
  type        = number
  default     = 10
}

variable "throttle_burst" {
  description = "API Gateway throttle burst limit"
  type        = number
  default     = 50
}

variable "custom_domain_name" {
  description = "API Gateway custom domain name to attach the base path mapping to"
  type        = string
}

variable "base_path" {
  description = "Base path for the API mapping (empty string for root, PR number for PR envs)"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
