locals {
  common_tags = {
    Project     = "humbugg"
    Environment = "development"
    ManagedBy   = "Terraform"
  }
}

module "auth" {
  source = "../../modules/auth"

  project     = "humbugg"
  environment = "development"
  tags        = local.common_tags
}
