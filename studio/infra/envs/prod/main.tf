locals {
  project     = "studio"
  environment = "prod"

  # The SPA's origin while it was deployed. Still named for the pool's callback
  # URLs and the media bucket's CORS rule; both are inert now that nothing
  # answers there, and both are cheaper to leave than to rewrite.
  app_domain = "studio.andreas.services"

  common_tags = {
    Project     = local.project
    Environment = local.environment
    Owner       = "ansavva"
    ManagedBy   = "terraform"
  }
}

data "aws_route53_zone" "main" {
  name         = "andreas.services"
  private_zone = false
}

data "aws_region" "current" {}

# The shared wildcard, for the Cognito custom auth domain below. The auth
# module cannot look it up itself, because `envs/dev` uses it too and declares
# no us-east-1 provider to alias in — so the ARN is resolved here and passed
# down.
data "aws_acm_certificate" "wildcard" {
  provider    = aws.us_east_1
  domain      = "*.andreas.services"
  statuses    = ["ISSUED"]
  most_recent = true
}

# THE MEDIA BUCKET.
#
# Studio owns this bucket: the generation pipeline that fills it lives in
# `.claude/skills/` alongside the app that reads it, so there is no other state
# with a claim on it.
#
# `prevent_destroy` means `terraform destroy` on this whole environment fails by
# design (see `modules/media/main.tf`). There is no second copy of this bucket
# anywhere, so versioning and that flag are the whole of its protection.
module "media" {
  source = "../../modules/media"

  bucket_name = var.media_bucket_name

  # The presigned-PUT rule the SPA used. Inert with the site gone; kept so a
  # re-deploy does not rediscover why it existed.
  cors_allowed_origins = ["https://${local.app_domain}"]

  tags = local.common_tags
}

module "auth" {
  source = "../../modules/auth"

  # The pool backs the whole app rather than an admin corner of it, so "app" is
  # the component it serves.
  name = "${local.project}-${local.environment}-app"

  # Exact-match, character for character. `localhost:5173` is registered
  # alongside the deployed origin because studio's SPA is routinely run from a
  # developer's machine against a real pool, and Vite's port is pinned at
  # `frontend/vite.config.ts` for exactly this reason — changing it breaks
  # sign-in with no apply to warn anyone.
  callback_urls = [
    "https://${local.app_domain}/auth/callback",
    "http://localhost:5173/auth/callback",
  ]

  # The bare origins: sign-out lands on the app's root, which then bounces
  # straight back through the hosted authorize page.
  logout_urls = [
    "https://${local.app_domain}/",
    "http://localhost:5173/",
  ]

  # `studio-auth`, not `auth.studio`: the shared wildcard covers one label.
  auth_domain          = "studio-auth.andreas.services"
  auth_certificate_arn = data.aws_acm_certificate.wildcard.arn
  route53_zone_id      = data.aws_route53_zone.main.zone_id

  tags = local.common_tags
}

# THE CATALOG.
#
# The bucket above holds the bytes; this holds the library. Identity, name,
# parent and owner are rows here, and an S3 key is an opaque `blob_key` nothing
# derives or parses — so rename, move and share are row writes that
# touch zero objects, and a lost row is a lost file even though every byte of it
# survives. `modules/catalog` carries the full reasoning.
#
# The name is composed here rather than taken from a variable, because there is
# nothing to decide: `[project]-[env]-[component]` gives `studio-prod-catalog`
# and no other value is correct. Changing it is a destroy-and-recreate that
# takes every row with it.
#
# PITR is left at the module's default of ON. It is the only recovery this data
# has.
module "catalog" {
  source = "../../modules/catalog"

  table_name = "${local.project}-${local.environment}-catalog"

  tags = local.common_tags
}

# SHUT DOWN, 2026-09-14. The site and the API are gone; the library stays.
#
# This root used to declare the whole app — the API Lambda and its ECR image
# (`modules/compute`), the REST gateway and `studio-api.andreas.services`
# (`modules/api_gateway`, `modules/api_domain`), the callback gateway and its
# worker (`modules/callbacks`), the render queue and its worker
# (`modules/render`), the SPA bucket, CloudFront and `studio.andreas.services`
# (`modules/hosting`), and the provider-token SecureString. All of it was
# regenerable from git and all of it was removed in one apply. What is left is
# what is not: the media bucket, the catalog table and the pool — the pool
# because every membership and favorite row is keyed by a Cognito `sub`, so a
# new pool would orphan the library's rows.
#
# Bringing it back is `git log` on this file, not a rebuild.

# THE SHARED DEV-SEED BUCKET, DECLARED HERE ON PURPOSE.
#
# It serves the dev environment and it is named for that — `studio-dev-seed-…`,
# the convention's `[project]-[env]-[component]-[region]` — but its LIFECYCLE is
# account-level, and this is the only studio root with an account-level
# lifecycle. `envs/dev` is per machine and is torn down by
# `dev-aws-destroy.sh`; a bucket every developer's stack is seeded from must not
# be reachable by a teardown, and a third root nothing applies would leave the
# bucket a design note rather than a resource.
#
# So: name and tags say DEV, because that is who it serves; the root says PROD,
# because that is what owns and applies it. `Environment` is overridden below
# rather than inherited so the tag and the name cannot disagree — a stray bucket
# is found by its tags or not at all.
#
# It carries `prevent_destroy`, as the media bucket above does, which is another
# reason it belongs in a root that is never destroyed on purpose.
module "dev_seed" {
  source = "../../modules/dev_seed"

  bucket_name = "${local.project}-dev-seed-${data.aws_region.current.region}"

  tags = merge(local.common_tags, {
    Environment = "dev"
  })
}
