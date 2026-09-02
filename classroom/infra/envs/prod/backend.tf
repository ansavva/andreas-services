terraform {
  backend "s3" {
    bucket = "andreas-services-terraform-state"
    key    = "classroom/prod/terraform.tfstate"
    region = "us-east-1"
  }
}
