variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "aws_region" {
  description = "Region the API and its Lambdas live in — the management endpoint is built from it"
  type        = string
}

variable "image_uri" {
  description = "The backend container image both Lambdas run; the deploy workflow repins it to :sha"
  type        = string
}

variable "lambda_role_arn" {
  description = "The API Lambda's execution role, which both realtime Lambdas run under (it already holds the table grant)"
  type        = string
}

variable "lambda_role_name" {
  description = "Name of that role, for the ManageConnections grant declared here"
  type        = string
}

variable "connections_table_name" {
  description = "DynamoDB table holding connections and one-time tickets"
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
