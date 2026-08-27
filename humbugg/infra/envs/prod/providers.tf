terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      # aws_cognito_managed_login_branding is what forces the 6.x line: it exists in no 5.x release and none before 6.12.
      # refresh_token_rotation is not the binding constraint — it has been available since 5.98.
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
