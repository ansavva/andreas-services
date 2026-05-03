# envs/dev/backend.tf
# Remote state configuration for development environment

terraform {
  backend "s3" {
    bucket  = "andreas-services-terraform-state"
    key     = "storybook/dev/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}
