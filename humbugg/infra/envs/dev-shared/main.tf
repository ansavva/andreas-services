# THE ONE THING EVERY DEV STACK SHARES: the Cognito pool.
#
# Every other development resource is per machine — tables, bucket, webhook
# relay — and stays that way. The pool moved out of `envs/dev` in September
# 2026 for one reason: social sign-in. Each provider's console holds a list of
# exact redirect URIs, and a per-machine pool means a per-machine Managed Login
# domain, which means every new machine is a console edit at Google, Meta,
# LinkedIn and Apple before its developer can sign in with any of them. One
# pool is one domain is one URI, registered once:
#
#   https://humbugg-dev.auth.us-east-1.amazoncognito.com/oauth2/idpresponse
#
# What sharing costs: accounts are shared. A `.test` person seeded on one
# machine exists for every machine, with whatever password the LAST seed set —
# `ensure_pool_user` converges the password every run. Per-machine tables still
# hold per-machine data; only the identities are common. And `dev-aws-reset.sh`
# no longer deletes users, because they are not one machine's to delete.
#
# Applied by `dev-aws-setup.sh` on every machine, every run, before the
# per-machine stack. Idempotent, so whoever runs it last is irrelevant —
# EXCEPT that the social credentials must come from somewhere every machine
# can read, or the second developer's apply would remove the providers the
# first one added. They come from SSM, `/humbugg/dev/social/*`, put there once
# by hand; `docs/auth-social-login.md` has the commands.

locals {
  project     = "humbugg"
  environment = "dev"

  common_tags = {
    Project     = local.project
    Environment = "development"
    ManagedBy   = "Terraform"
    LastApplied = var.aws_principal_arn
  }
}

# Whatever exists under the path, decrypted; an empty path is an empty map,
# not an error, which is what lets a stack apply before any credential does.
data "aws_ssm_parameters_by_path" "social" {
  path            = "/${local.project}/${local.environment}/social"
  with_decryption = true
}

locals {
  social = zipmap(
    [for name in data.aws_ssm_parameters_by_path.social.names : basename(name)],
    data.aws_ssm_parameters_by_path.social.values,
  )
  # Every value off that data source is sensitive, secrets and ids alike, and
  # sensitivity is contagious: the ids decide WHICH providers exist, so the
  # provider list, the Lambda's environment and this stack's outputs would all
  # inherit it. The ids are public — they are in every authorize URL — so they
  # are unwrapped here; the secrets never are.
  id = { for key in [
    "google-client-id", "facebook-app-id",
    "apple-services-id", "apple-team-id", "apple-key-id",
    "linkedin-client-id",
  ] : key => nonsensitive(lookup(local.social, key, "")) }
}

module "auth" {
  source = "../../modules/auth"

  project     = local.project
  environment = local.environment

  # 8081 is Metro, the one surface that authenticates; the scheme is the store
  # build's. Identical on every machine, which is part of why one pool works.
  callback_urls = ["http://localhost:8081/auth/callback", "humbugg://auth/callback"]
  logout_urls   = ["http://localhost:8081/login", "humbugg://auth/logout"]

  # A DEFAULT Cognito domain, fixed by the prefix. A custom `auth-dev.humbugg.com`
  # would cost a SAN on the prod certificate — a replacement — for a page no
  # user ever loads.
  auth_domain_prefix = "${local.project}-${local.environment}"

  google_client_id       = local.id["google-client-id"]
  google_client_secret   = lookup(local.social, "google-client-secret", "")
  facebook_app_id        = local.id["facebook-app-id"]
  facebook_app_secret    = lookup(local.social, "facebook-app-secret", "")
  apple_services_id      = local.id["apple-services-id"]
  apple_team_id          = local.id["apple-team-id"]
  apple_key_id           = local.id["apple-key-id"]
  apple_private_key      = lookup(local.social, "apple-private-key", "")
  linkedin_client_id     = local.id["linkedin-client-id"]
  linkedin_client_secret = lookup(local.social, "linkedin-client-secret", "")

  tags = local.common_tags
}

# How a per-machine stack finds the pool: three parameters, the same names prod
# publishes under `/humbugg/prod/`. `envs/dev` reads them as data sources, so a
# machine set up before this stack exists fails its plan with the parameter's
# name in the error rather than with a pool that is not there.
resource "aws_ssm_parameter" "user_pool_id" {
  name  = "/${local.project}/${local.environment}/cognito-user-pool-id"
  type  = "String"
  value = module.auth.user_pool_id
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "client_id" {
  name  = "/${local.project}/${local.environment}/cognito-client-id"
  type  = "String"
  value = module.auth.user_pool_client_id
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "auth_domain" {
  name  = "/${local.project}/${local.environment}/cognito-auth-domain"
  type  = "String"
  value = module.auth.auth_domain
  tags  = local.common_tags
}
