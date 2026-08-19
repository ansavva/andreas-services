# STUDIO'S PER-MACHINE DEVELOPMENT ENVIRONMENT.
#
# Studio ran local-against-prod until August 2026 — one bucket, one pool, no
# seed data — on the reasoning that an empty second bucket would exercise none
# of the behaviour that matters. This environment is the other half of the
# answer: real per-machine AWS resources, seeded with real media copied down
# from a shared seed bucket. Not LocalStack, not moto.
#
# The mechanism is a verbatim port of humbugg's, down to the state key layout,
# so it is learned once and applies to both services. Everything is keyed by a
# persistent UUID in `~/.config/andreas-services/studio/machine-id`; the
# `dev-aws-*.sh` scripts read it and pass it in. Nothing here is applied by CI,
# and no tfvars file is committed — see `terraform.tfvars.example`.
#
# What this environment deliberately does NOT declare: hosting, CloudFront,
# API Gateway, the custom API domain, ECR, or the Lambda. The dev backend is
# Flask on `:8000` under `dev-up.sh` and the SPA is Vite on `:5173`, both
# talking to the real AWS resources below. A per-machine CloudFront
# distribution would cost 20 minutes per apply and per destroy to prove
# nothing.

locals {
  project     = "studio"
  environment = "dev"

  # `studio-dev-<short12>` — the prefix `dev-aws-common.sh` computes as
  # RESOURCE_PREFIX. The 12 hex characters are the front of the machine UUID,
  # which is what keeps two developers (or one developer's two machines) from
  # colliding in a single shared AWS account.
  resource_prefix = "${local.project}-${local.environment}-${var.machine_short_id}"

  # S3 names are globally unique, so this one carries the region suffix the
  # convention reserves for buckets. The region comes from the variable the
  # provider below is configured with, rather than a `data.aws_region`, so the
  # name is knowable at plan time without a call.
  media_bucket_name = "${local.resource_prefix}-media-${var.aws_region}"

  # `[project]-[env]-[component]`, with the machine id inside the env segment.
  catalog_table_name = "${local.resource_prefix}-catalog"

  # The caller ARN's trailing path segment — `user/ansavva` gives `ansavva`,
  # an assumed-role ARN gives the session name. Used for the `Owner` tag the
  # repo convention requires on every resource; `DeveloperPrincipal` keeps the
  # full ARN, which is the value that actually identifies the caller.
  principal_name = element(
    split("/", var.aws_principal_arn),
    length(split("/", var.aws_principal_arn)) - 1
  )

  # The four tags every resource in this repo carries, plus the three that make
  # a per-machine resource traceable. These resources live in the same account
  # as prod and outlive the terminal that created them; a stray dev bucket is
  # found by its tags or not at all.
  common_tags = {
    Project     = local.project
    Environment = local.environment
    Owner       = local.principal_name
    ManagedBy   = "terraform"

    DeveloperMachineId = var.machine_id
    DeveloperPrincipal = var.aws_principal_arn
    MachineName        = var.machine_name
  }
}

# A dev pool of studio's own, so signing in locally stops meaning signing in to
# the live one. Same module as prod — admin-create-only, secretless SRP client,
# no hosted UI — so the SPA's auth path is the real one. Accounts come from
# `scripts/create-user.sh` pointed at this pool.
module "auth" {
  source = "../../modules/auth"

  # `-app`, as in prod: the pool backs the whole app rather than a corner of it.
  name = "${local.resource_prefix}-app"
  tags = local.common_tags
}

# The media bucket and the catalog table, from the disposable module rather than
# `modules/media` + `modules/catalog`. `prevent_destroy` takes a literal, so a
# bucket `dev-aws-destroy.sh` can delete cannot come from the module guarding
# the prod one — see `modules/dev_storage/main.tf`.
module "storage" {
  source = "../../modules/dev_storage"

  media_bucket_name  = local.media_bucket_name
  catalog_table_name = local.catalog_table_name

  tags = local.common_tags
}
