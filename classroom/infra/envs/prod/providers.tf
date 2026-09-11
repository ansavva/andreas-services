terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

# CloudFront and Cognito custom domains both require a us-east-1 certificate.
# The service already runs in us-east-1, so this alias is about being explicit
# rather than about crossing regions.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}
