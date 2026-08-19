terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# One provider only. `envs/prod` also declares a `us_east_1` alias for the
# CloudFront certificate and the edge function; this environment has no
# CloudFront, so it has no second provider either.
provider "aws" {
  region = var.aws_region

  # The state key `dev-aws-common.sh` computes embeds the account id, so state
  # and account are bound together outside Terraform. This binds them inside
  # it: exported credentials for a different account fail here rather than
  # creating a second set of per-machine resources somewhere unexpected.
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = local.common_tags
  }
}
