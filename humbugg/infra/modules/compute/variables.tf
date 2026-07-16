variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "dynamodb_table_arns" {
  description = "Map of DynamoDB table ARNs the Lambda needs access to"
  type        = map(string)
  default     = {}
}

variable "cognito_user_pool_id" {
  description = "Cognito user pool used to authorize API requests"
  type        = string
}

variable "cognito_client_id" {
  description = "Cognito web client accepted by the API authorizer"
  type        = string
}

variable "ses_identity_arn" {
  description = "SES domain identity the backend may use for transactional email"
  type        = string
}

variable "email_messages_table_arn" {
  description = "DynamoDB delivery-ledger table ARN"
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
