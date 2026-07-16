variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "humbugg_role_name" {
  description = "Existing Humbugg backend Lambda execution role"
  type        = string
  default     = "humbugg-lambda-role-production"
}
