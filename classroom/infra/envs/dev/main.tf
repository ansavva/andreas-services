# CLASSROOM'S PER-MACHINE DEVELOPMENT ENVIRONMENT.
#
# The mechanism is a port of studio's and humbugg's, down to the state key
# layout, so it is learned once and applies to all three. Everything is keyed by
# a persistent UUID in `~/.config/andreas-services/classroom/machine-id`; the
# `dev-aws-*.sh` scripts read it and pass it in. Nothing here is applied by CI,
# and no tfvars file is committed — see `terraform.tfvars.example`.
#
# What this environment deliberately does NOT declare: hosting, CloudFront, the
# custom API domain, ECR, the API Lambda, or the API Gateway in front of it. The
# dev backend is Flask on `:8001` under `dev-up.sh` and the SPA is Vite on
# `:5174`, both against the real Cognito pool and the real table below. A
# per-machine CloudFront distribution would cost twenty minutes per apply and
# per destroy to prove nothing.
#
# **Declining the API Gateway is not free, and it is worth saying what it
# costs.** In prod the gateway is the authorizer: it verifies the ID token and
# hands Flask the claims on the event, which is why `classroom_core/auth.py`
# verifies no signature of its own. Locally there is no gateway, so
# `handlers/local/api/api_dev_server.py` does that job — it verifies against
# THIS pool's JWKS and puts the claims where the gateway would have. That file
# also mirrors the gateway's route split (`/api/public/*` anonymous and GET-only,
# everything else authenticated), because that split is the security model and
# a local server more permissive than prod is a local server that hides bugs.

locals {
  project     = "classroom"
  environment = "dev"

  # `classroom-dev-<short12>` — the prefix `dev-aws-common.sh` computes as
  # RESOURCE_PREFIX. The 12 hex characters are the front of the machine UUID,
  # which is what keeps two developers (or one developer's two machines) from
  # colliding in a single shared AWS account.
  resource_prefix = "${local.project}-${local.environment}-${var.machine_short_id}"

  # The caller ARN's trailing path segment — `user/ansavva` gives `ansavva`, an
  # assumed-role ARN gives the session name. Used for the `Owner` tag the repo
  # convention requires; `DeveloperPrincipal` keeps the full ARN, which is the
  # value that actually identifies the caller.
  principal_name = element(
    split("/", var.aws_principal_arn),
    length(split("/", var.aws_principal_arn)) - 1
  )

  # The four tags every resource in this repo carries, plus the three that make
  # a per-machine resource traceable. These live in the same account as prod and
  # outlive the terminal that created them; a stray dev table is found by its
  # tags or not at all.
  common_tags = {
    Project     = local.project
    Environment = local.environment
    Owner       = local.principal_name
    ManagedBy   = "Terraform"

    DeveloperMachineId = var.machine_id
    DeveloperPrincipal = var.aws_principal_arn
    MachineName        = var.machine_name
  }
}

# A dev pool of classroom's own, so signing in locally stops meaning signing in
# to the live one. The same module as prod — admin-create-only, secretless
# client, PKCE-only code flow — so the SPA's auth path is the real one, not a
# stub. The account in it comes from `scripts/dev-user.sh`.
#
# **This is also why the dev stack is not optional.** Every page is keyed by the
# Cognito `sub`, so developing against prod's pool means writing rows next to a
# real teacher's under a real teacher's key.
module "auth" {
  source = "../../modules/auth"

  name = local.resource_prefix

  # **A default Cognito domain, not a custom one.** `classroom-dev-<short12>` is
  # already unique per machine, which is what a domain prefix has to be, and it
  # needs no certificate and no DNS record — so a stack applies and destroys in
  # seconds. It is also the only option here: this environment declares no
  # us-east-1 provider and reads no ACM certificate, and neither should be added
  # for a sign-in page. The full host comes back out as `cognito_domain`.
  auth_domain_prefix = local.resource_prefix

  # Only localhost. There is no deployed origin in this environment. Exact
  # match, character for character, including the port — see `CALLBACK_PATH` in
  # frontend/src/auth/oauth.ts.
  callback_urls = ["${var.spa_origin}/auth/callback"]
  logout_urls   = ["${var.spa_origin}/"]

  tags = local.common_tags
}

# The pages table, from the same module prod uses. The machine id sits inside
# the environment segment, so the name is `classroom-dev-<short12>-pages` and
# still reads `[project]-[env]-[component]` left to right.
#
# Same module rather than a disposable copy because there is nothing to guard
# against: this table carries no `prevent_destroy` and no `force_destroy`
# equivalent, so `dev-aws-destroy.sh` can delete it as it stands. Studio needed
# a separate `dev_storage` module only because its prod BUCKET is pinned.
# A lesson's uploaded files, per machine. There is no distribution in front of
# it: `dev-up.sh` serves `/lesson/<id>/*` from the local API, reading these
# objects with the developer's own credentials.
#
# The origin split that protects a teacher in production holds locally too, and
# for free — the SPA is `localhost:5174` and the API serving lessons is
# `localhost:8001`, and an origin includes its port.
module "lessons" {
  source = "../../modules/lessons"

  bucket_name    = "${local.resource_prefix}-lessons-${var.aws_region}"
  upload_origins = [var.spa_origin]

  tags = local.common_tags
}

module "data" {
  source = "../../modules/data"

  project     = local.project
  environment = "${local.environment}-${var.machine_short_id}"

  tags = local.common_tags
}
