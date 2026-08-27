terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      # aws_cognito_managed_login_branding lands in 6.12.0 and is the binding
      # constraint — hence the 5.x -> 6.x major bump. refresh_token_rotation
      # lands in 5.98.0 and is deliberately unused here. Both bisected against
      # the registry; the changelog dates circulating for them are wrong.
      source  = "hashicorp/aws"
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
