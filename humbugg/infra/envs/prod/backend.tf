terraform {
  backend "s3" {
    bucket  = "andreas-services-terraform-state"
    key     = "humbugg/prod/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}
