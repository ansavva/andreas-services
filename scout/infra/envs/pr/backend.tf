terraform {
  backend "s3" {
    bucket  = "andreas-services-terraform-state"
    region  = "us-east-1"
    encrypt = true
    # key is injected at init time:
    # terraform init -backend-config="key=scout/pr/<N>/terraform.tfstate"
  }
}
