terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # **A major bump, and 6.12 is not a guess.** `aws_cognito_managed_login_branding`
      # — which `modules/auth` must create, or the v2 domain serves "Login pages
      # unavailable" — does not exist anywhere in the 5.x line and first appears
      # in 6.12.0. Measured: 5.100.0 (the last 5.x), 6.0, 6.5, 6.10 and 6.11 all
      # fail `terraform validate` with "does not support resource type"; 6.12
      # passes. The epic plan's `>= 5.94, < 6.0` cannot work.
      version = ">= 6.12, < 7.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = local.common_tags
  }
}
