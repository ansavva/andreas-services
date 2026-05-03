# envs/prod/backend.tf
# Remote state configuration for production environment

terraform {
  backend "s3" {
    bucket  = "andreas-services-terraform-state"
    key     = "storybook/prod/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}
