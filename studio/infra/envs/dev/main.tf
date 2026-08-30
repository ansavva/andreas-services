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
# What this environment deliberately does NOT declare: hosting, CloudFront, the
# custom API domain, ECR, or the API Lambda. The dev backend is Flask on `:8000`
# under `dev-up.sh` and the SPA is Vite on `:5173`, both talking to the real AWS
# resources below. A per-machine CloudFront distribution would cost 20 minutes
# per apply and per destroy to prove nothing.
#
# **It DOES declare an API Gateway now, and that sentence used to say it never
# would.** The exception is `module.callbacks`, and it is worth stating why it
# earns one when hosting does not.
#
# Replicate cannot reach `http://localhost:8000`. So for as long as this
# environment had no public endpoint, the callback that closes a generation
# could not be exercised on a developer's machine at all — local development
# fell back to polling, and the code that closes a run in production was code
# nobody had ever run outside a unit test. That is not a convenience gap; it is
# the most expensive path in studio being unreachable from the place it is
# written.
#
# What makes it affordable is that the deployed half is tiny and fixed. The
# receiver is a single dependency-free file, packaged as a zip straight from the
# repo — no ECR, no image build, no deploy step — and all it does is put the
# callback on a queue. **The half that changes is not deployed at all**:
# `dev-up.sh` runs a consumer that long-polls that queue and closes the run with
# the working tree. So a real, signed Replicate callback reaches the code being
# edited, and an apply here is still seconds.

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
# the live one. Same module as prod — admin-create-only, secretless client, its
# own Managed Login pages — so the SPA's auth path is the real one. Accounts
# come from `scripts/create-user.sh` pointed at this pool.
module "auth" {
  source = "../../modules/auth"

  # `-app`, as in prod: the pool backs the whole app rather than a corner of it.
  name = "${local.resource_prefix}-app"

  # **A default Cognito domain, not a custom one.** `studio-dev-<short12>` is
  # already unique per machine, which is what a domain prefix has to be, and it
  # needs no certificate and no DNS record — so a stack applies and destroys in
  # seconds rather than carrying a ~15-minute custom-domain apply each way. It
  # is also the only option here: this environment declares no hosting, no
  # CloudFront and no us-east-1 provider, and none of that should be added for
  # a sign-in page. The full host comes back out as `cognito_auth_domain`.
  auth_domain_prefix = local.resource_prefix

  # Only localhost. There is no deployed origin in this environment — the SPA
  # is Vite on :5173 and the API is Flask on :8000.
  callback_urls = ["http://localhost:5173/auth/callback"]
  logout_urls   = ["http://localhost:5173/"]

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

  # Passed explicitly even though the module defaults to the same value, so the
  # one thing that differs between this bucket's CORS rule and prod's is visible
  # here rather than only in the module.
  cors_allowed_origins = var.spa_origins

  tags = local.common_tags
}


# WHERE A FINISHED GENERATION IS REPORTED — PER MACHINE.
#
# The same module prod uses, minus the worker. `worker_image_uri` is left unset,
# so no consumer Lambda is created and nothing here needs an ECR repository or
# the API's execution role; what drains the queue is a process beside
# `dev-up.sh`, running this checkout. See the note at the top of this file.
#
# The URL is an `execute-api` hostname rather than anything under
# `andreas.services`: it is called by one machine that is told where to call,
# never typed, so a DNS record and a certificate would buy nothing and cost a
# minute per apply.
module "callbacks" {
  source = "../../modules/callbacks"

  name_prefix = local.resource_prefix

  # No `worker_image_uri`, no `replicate_token_parameter`, no bucket and no
  # table. Every one of those is the worker's, and there is no worker here — the
  # local consumer reads the developer's own environment and their own AWS key.

  tags = local.common_tags
}

# THE RENDER QUEUE. A QUEUE AND NOTHING ELSE, FOR THE SAME REASON AS ABOVE.
#
# `create_ecr` and `create_worker` are both false here: a per-machine image build
# would cost minutes per apply, and the render image is the larger of the two —
# it carries ffmpeg. So this environment gets the queue, and `dev-up.sh` runs
# `handlers/local/consumer/render_consumer.py` beside the API to drain it with
# the developer's own working tree and their own ffmpeg.
#
# That is the same arrangement callbacks has, and it buys the same thing: the
# code that stitches a scene in production is code a developer has run.
#
# **No `api_role_name` either.** The API here is a process under a developer's own
# IAM key, not a Lambda with a role to attach a grant to — so the `SendMessage`
# that reaches this queue is authorised by that key, which already holds it.
module "render" {
  source = "../../modules/render"

  name_prefix = local.resource_prefix

  tags = local.common_tags
}
