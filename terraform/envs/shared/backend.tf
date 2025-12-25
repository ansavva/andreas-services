# envs/shared/backend.tf
# Remote state for shared platform infrastructure

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket  = "andreas-services-terraform-state"
    key     = "root/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}
