terraform {
  backend "s3" {
    bucket  = "andreas-services-terraform-state"
    key     = "scout/pr-preview/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}
