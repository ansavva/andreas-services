locals {
  project     = "studio"
  environment = "prod"

  app_domain = "studio.andreas.services"

  # `studio-api`, not `api.studio`: the shared wildcard certificate covers one
  # label, so a second level would need a certificate of its own. Same shape as
  # website-api.andreas.services.
  api_domain = "studio-api.andreas.services"

  # **A literal, and it has to be one.** Both the parameter below and the IAM
  # grant in `modules/compute` are built from this string; taking the name off
  # the resource instead made the grant's `count` unresolvable at plan time and
  # failed a prod deploy with `Invalid count argument`. `terraform validate`
  # does not resolve references between resources, so nothing caught it until a
  # real plan ran.
  replicate_token_name = "/studio/prod/replicate-api-token"

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

# The shared wildcard, for the Cognito custom auth domain below. The hosting
# and api_domain modules each look this up for themselves; the auth module
# cannot, because `envs/dev` uses it too and declares no us-east-1 provider to
# alias in — so the ARN is resolved here and passed down.
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
#
# `module.compute` takes its bucket name from the module rather than a bare
# string, so the IAM policy that grants access has a real dependency edge on the
# bucket it grants access to.

module "media" {
  source = "../../modules/media"

  bucket_name = var.media_bucket_name

  # Built from `local.app_domain`, like the API's `allowed_origin` below, so the
  # two CORS surfaces cannot come to name different hostnames for one SPA. This
  # one is about the presigned PUT only: the upload's bytes go browser → S3 and
  # never through the API.
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

  # `studio-auth`, not `auth.studio`: the shared wildcard covers one label, the
  # same constraint that gave `studio-api` its name above.
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

# THE PROVIDER TOKEN. **THE ONLY SECRET STUDIO HOLDS.**
#
# Declared here rather than inside a module because two of them read it: the API
# Lambda, which creates predictions, and the callback worker, which asks about
# them. Neither should own a resource the other depends on.
#
# **Terraform creates the parameter and never the value.** `ignore_changes` on
# `value` is what makes that true rather than aspirational: the placeholder below
# is written once, on the apply that creates the parameter, and the real token
# written afterwards survives every subsequent apply.
#
# **The writer is `studio-prod.yaml`, from the `REPLICATE_API_TOKEN` environment
# secret on `studio-production`.** It puts the value here on every app deploy, so
# rotating the token is "update the secret, re-run the workflow" and nothing has
# to be remembered about SSM at all.
#
# The alternative — a `TF_VAR_replicate_api_token` — would put the secret in the
# plan output and in the state file, which is why the value travels through the
# workflow's `put-parameter` rather than through this resource.
#
# Until the secret is set, `POST /api/runs/<id>/submit` answers 500 with a
# message naming this parameter, and nothing else in studio is affected —
# browsing, listing and every read route are untouched.
#
# **This is the first SecureString in the account**, and writing one needs
# `kms:Encrypt` through SSM in the CI role — a grant that lives in
# `infra/envs/shared` and is applied by a DIFFERENT workflow. The shared apply
# has to land before studio's next deploy, or that deploy fails at this resource
# with an error naming a service nobody changed.
resource "aws_ssm_parameter" "replicate_api_token" {
  name        = local.replicate_token_name
  description = "Replicate API token. Written by studio-prod.yaml from a GitHub environment secret; Terraform never holds the value."
  type        = "SecureString"
  value       = "placeholder-the-deploy-workflow-writes-the-real-one"

  tags = local.common_tags

  lifecycle {
    ignore_changes = [value]
  }
}

module "compute" {
  source = "../../modules/compute"

  project     = local.project
  environment = local.environment

  # A NAME and an ARN, never the value. The API reads the parameter at call time
  # so the token never sits in the function's environment, where
  # `lambda:GetFunctionConfiguration` would hand it to anyone who can list the
  # account. The ARN scopes the grant to this one parameter.
  # The NAME as a literal, never the resource's attribute — that is what keeps
  # the grant's `count` resolvable at plan time. The module composes the ARN.
  replicate_token_parameter = local.replicate_token_name

  # From the module, not from the variable directly: this is what orders the
  # IAM policy after the bucket exists.
  media_bucket_name = module.media.bucket_name
  allowed_origin    = "https://${local.app_domain}"

  # Same reasoning, one step further: the ARN comes from the module so the item
  # grants are ordered after the table, and the name comes from the module so
  # the env var cannot name a table this state did not create.
  catalog_table_name = module.catalog.table_name
  catalog_table_arn  = module.catalog.table_arn

  # The Lambda validates the JWT itself; the gateway's authorizer stays as the
  # outer gate but its claims cannot reach Flask. These are the same two ids the
  # SPA is built with and `dev-setup.sh` writes into `.env.local`, so all three
  # surfaces track one pool by construction.
  cognito_user_pool_id = module.auth.user_pool_id
  cognito_client_id    = module.auth.user_pool_client_id

  tags = local.common_tags
}

module "api_domain" {
  source = "../../modules/api_domain"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  domain_name     = local.api_domain
  route53_zone_id = data.aws_route53_zone.main.zone_id
  tags            = local.common_tags
}

module "api_gateway" {
  source = "../../modules/api_gateway"

  project     = local.project
  environment = local.environment

  lambda_invoke_arn    = module.compute.api_invoke_arn
  lambda_function_name = module.compute.api_function_name

  custom_domain_name = module.api_domain.domain_name
  base_path          = ""
  stage_name         = "prod"

  cognito_user_pool_arn = module.auth.user_pool_arn
  allowed_origin        = "https://${local.app_domain}"

  throttle_rate  = var.api_throttling_rate_limit
  throttle_burst = var.api_throttling_burst_limit

  tags = local.common_tags
}

# WHERE A FINISHED GENERATION IS REPORTED, AND WHAT CLOSES THE RUN.
#
# Its own gateway, deliberately, and `modules/callbacks/main.tf` argues the
# whole case. The short version: a callback cannot hold a Cognito token, so on
# the API's gateway it would have been the second unauthenticated exception and
# the first one that writes. Here there is no authorizer to carve an exception
# out of — one route, reaching a function that can do nothing but enqueue.
#
# The worker runs the API's image at a different handler and under the API's own
# role: the work is identical, and a second role would be a hand-kept copy of
# `modules/compute`'s policies that drifts. It is sized for what it does — a
# video download and an upload — which is why the API Lambda did NOT have to
# grow to absorb this.
module "callbacks" {
  source = "../../modules/callbacks"

  name_prefix = "${local.project}-${local.environment}"

  media_bucket_name = module.media.bucket_name

  catalog_table_name        = module.catalog.table_name
  replicate_token_parameter = local.replicate_token_name

  # `:latest`, matching the Lambda in `modules/compute`: the deploy workflow
  # repoints both to `:${{ github.sha }}` after the image is pushed, and both
  # carry `ignore_changes = [image_uri]` so Terraform sets it once.
  #
  # **A non-empty value here is what creates the worker at all.** `envs/dev`
  # passes nothing, has no ECR repository, and drains the queue from a laptop.
  # **`create_worker` is an explicit flag, not an inference from the image URI**,
  # and that is the same plan-time lesson one module over. Deriving it from
  # `module.compute.ecr_repository_url` keyed a `count` on a resource attribute,
  # which resolves only because prod's ECR repository already exists — on a
  # fresh account it would fail the plan exactly as the token grant did.
  create_worker    = true
  worker_image_uri = "${module.compute.ecr_repository_url}:latest"
  worker_role_arn  = module.compute.api_role_arn
  worker_role_name = module.compute.api_role_name

  tags = local.common_tags
}

# WHERE A STITCH HAPPENS.
#
# `modules/render/main.tf` argues the whole case; the short version is that
# stitching needs `ffmpeg`, and this is a **second image** rather than ffmpeg
# in the API's: an 80 MB video toolchain should not be
# pulled on every cold start of a function that answers folder listings, and a
# re-encode is minutes against API Gateway's 30-second ceiling.
#
# It takes a role of its own, unlike the callback worker, which shares the API's.
# The premise there — "it does exactly what the API does" — does not hold here:
# this worker never calls Replicate, so the API's role would hand it the provider
# token and the ability to spend money for a code path that does not exist. The
# two policy DOCUMENTS come across instead, so there is one definition of what
# library access means and two roles scoped to two jobs.
module "render" {
  source = "../../modules/render"

  name_prefix = "${local.project}-${local.environment}"

  # **Literals, for the plan-time reason `modules/compute` failed a deploy on.**
  # A `count` that depends on a resource attribute cannot be resolved before
  # anything is created, and both of these drive one.
  create_ecr    = true
  create_worker = true

  # No `worker_image_uri`: the module composes `<account>.dkr.ecr.<region>
  # .amazonaws.com/studio-prod-render:latest` from literals, because it declares
  # both the repository and the function and passing its own output back in
  # would be a cycle. The deploy workflow repoints the function to
  # `:${{ github.sha }}` afterwards, and `ignore_changes = [image_uri]` means
  # Terraform sets it once.

  # The API's grant to enqueue, attached to the API's role from inside the module
  # that declares the queue — the same arrangement `modules/callbacks` uses for
  # the worker's drain grant, and for the same reason: neither module should own
  # a resource the other depends on.
  create_api_grant = true
  api_role_name    = module.compute.api_role_name

  # One definition of library access, two roles. See the outputs in
  # `modules/compute` for why this is documents rather than the role.
  media_access_policy   = module.compute.media_access_policy
  catalog_access_policy = module.compute.catalog_access_policy

  media_bucket_name  = module.media.bucket_name
  catalog_table_name = module.catalog.table_name

  tags = local.common_tags
}

# `update-lambda` reads this back and sets it on the API Lambda as
# `STUDIO_RENDER_QUEUE_URL`. Through SSM rather than through `modules/compute`'s
# `environment` block for the reason the callback URL travels the same way: that
# block carries `ignore_changes` and applies once at creation, and the workflow
# is what sets every variable on a running function.
resource "aws_ssm_parameter" "render_queue_url" {
  name        = "/${local.project}/${local.environment}/render-queue-url"
  description = "SQS queue the API enqueues render jobs onto"
  type        = "String"
  value       = module.render.queue_url

  tags = local.common_tags
}

# Terraform knows where callbacks arrive; `update-lambda` reads this back and
# sets it on the API Lambda as `STUDIO_WEBHOOK_BASE_URL`.
#
# **Through SSM rather than through the module's `environment` block**, and not
# for the usual reason. The block would be a dependency cycle: `modules/compute`
# is `modules/callbacks`'s input (it lends the worker its role), so it cannot
# also read that module's output. The workflow is what sets every variable on a
# running function in any case — see `modules/compute`'s `ignore_changes`.
resource "aws_ssm_parameter" "callback_base_url" {
  name        = "/${local.project}/${local.environment}/callback-base-url"
  description = "Origin Replicate is told to call back on when a prediction finishes"
  type        = "String"
  value       = module.callbacks.base_url

  tags = local.common_tags
}

module "hosting" {
  source = "../../modules/hosting"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  project     = local.project
  environment = local.environment
  domain_name = local.app_domain

  # S3 names are globally unique, so this one carries the region suffix the
  # convention reserves for buckets.
  app_bucket_name = "${local.project}-${local.environment}-app-${data.aws_region.current.region}"

  route53_zone_id = data.aws_route53_zone.main.zone_id
  tags            = local.common_tags
}

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
