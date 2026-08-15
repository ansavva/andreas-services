terraform {
  backend "s3" {
    bucket  = "andreas-services-terraform-state"
    key     = "studio/prod/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}
