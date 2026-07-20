locals {
  resource_prefix = "humbugg-dev-${var.machine_short_id}"
  app_bucket_name = "humbugg-dev-${var.aws_account_id}-${var.machine_short_id}-app"

  common_tags = {
    Project            = "humbugg"
    Environment        = "development"
    ManagedBy          = "Terraform"
    DeveloperMachineId = var.machine_id
    DeveloperPrincipal = var.aws_principal_arn
    MachineName        = var.machine_name
  }
}

module "auth" {
  source = "../../modules/auth"

  project       = local.resource_prefix
  environment   = "development"
  callback_urls = ["http://localhost:5173"]
  logout_urls   = ["http://localhost:5173"]
  tags          = local.common_tags
}

module "storage" {
  source = "../../modules/dev_storage"

  resource_prefix = local.resource_prefix
  app_bucket_name = local.app_bucket_name
  tags            = local.common_tags
}
