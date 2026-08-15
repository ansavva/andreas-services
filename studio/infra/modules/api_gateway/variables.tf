variable "project" {
  description = "Project name; the first segment of every resource name"
  type        = string
}

variable "environment" {
  description = "Deployment environment; the second segment of every resource name"
  type        = string
}

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
  default     = 25
}

variable "throttle_burst" {
  description = "Burst request limit"
  type        = number
  default     = 50
}

variable "cognito_user_pool_arn" {
  description = "Cognito user pool ARN backing the authorizer on every /api route"
  type        = string
}

variable "allowed_origin" {
  description = "Access-Control-Allow-Origin value for CORS preflight"
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
