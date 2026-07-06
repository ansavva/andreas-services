variable "lambda_invoke_arn" {
  description = "Invoke ARN of the API Lambda"
  type        = string
}

variable "lambda_function_name" {
  description = "Name of the API Lambda (for the invoke permission)"
  type        = string
}

variable "custom_domain_name" {
  description = "API Gateway custom domain to map the stage onto"
  type        = string
}

variable "base_path" {
  description = "Base path for the domain mapping (\"\" for root)"
  type        = string
  default     = ""
}

variable "stage_name" {
  description = "API Gateway stage name"
  type        = string
  default     = "prod"
}

variable "throttle_rate" {
  description = "Steady-state request rate limit"
  type        = number
  default     = 10
}

variable "throttle_burst" {
  description = "Burst request limit"
  type        = number
  default     = 50
}

variable "cognito_user_pool_arn" {
  description = "Cognito user pool ARN for the admin authorizer"
  type        = string
  default     = ""
}

variable "enable_cognito_authorizer" {
  description = "Whether to protect /api/admin/* with the Cognito authorizer"
  type        = bool
  default     = true
}

variable "allowed_origin" {
  description = "Access-Control-Allow-Origin value for CORS preflight"
  type        = string
  default     = "https://www.andreas.services"
}

variable "pr_number" {
  description = "PR number for ephemeral previews; \"\" for prod"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
