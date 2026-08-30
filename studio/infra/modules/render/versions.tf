terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source = "hashicorp/aws"
      # The major `envs/dev` and `envs/prod` both pin, so a standalone
      # `terraform validate` here sees the provider the environments use.
      version = ">= 6.12, < 7.0"
    }
  }
}
