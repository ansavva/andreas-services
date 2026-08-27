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

  project     = local.resource_prefix
  environment = "development"

  # 8081, not 5173: the product app is the only surface that authenticates and it
  # is served by Metro. 5173 is the marketing site, which signs nobody in — those
  # entries were stale from before the split and were never reachable, because
  # the client had no OAuth flow enabled to make them live.
  callback_urls = ["http://localhost:8081/auth/callback", "humbugg://auth/callback"]
  logout_urls   = ["http://localhost:8081/login", "humbugg://auth/logout"]

  # Dev stacks take a DEFAULT Cognito domain. A custom one would need a SAN on a
  # certificate, a hosted-zone record and a ~15-minute apply per machine, for
  # pages nobody but that machine's developer ever loads. The prefix must be
  # unique across all of AWS, which the per-machine id already guarantees.
  auth_domain_prefix = local.resource_prefix

  tags = local.common_tags
}

module "storage" {
  source = "../../modules/dev_storage"

  resource_prefix = local.resource_prefix
  app_bucket_name = local.app_bucket_name
  tags            = local.common_tags
}
