terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # `aws_cognito_managed_login_branding` lands in **6.12.0** — measured,
      # not read off a changelog: 6.11.0 rejects it as an invalid resource
      # type and no 5.x release has it at all. That is what forces scout off
      # the 5.x line the other services still float on.
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
