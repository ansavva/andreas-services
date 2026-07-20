terraform {
  backend "s3" {
    bucket  = "andreas-services-terraform-state"
    region  = "us-east-1"
    encrypt = true
  }
}
