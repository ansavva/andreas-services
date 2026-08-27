# Cognito user pool backing the studio app.
#
# There is no public sign-up and there is not meant to be one: this is a private
# viewer over a private bucket, so accounts are created out of band with
# `studio/scripts/create-user.sh` and `allow_admin_create_user_only` is what
# makes that the only route in. The SPA signs in through Cognito Managed Login
# (the hosted pages on the domain at the bottom of this file) and the API
# Gateway Cognito authorizer validates the ID token.
#
# **The CLI does not.** `studio login` authenticates with SRP against
# `InitiateAuth` and holds no browser — which is why the client below keeps
# `ALLOW_USER_SRP_AUTH` and `ALLOW_REFRESH_TOKEN_AUTH`, and why refresh-token
# rotation is not enabled here. Read the comment on `explicit_auth_flows`
# before changing either.
resource "aws_cognito_user_pool" "main" {
  name = var.name

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # **Case-insensitive email usernames — and this argument REPLACES THE POOL.**
  #
  # AWS accepts `username_configuration` only at pool creation, so the provider
  # marks it ForceNew: the apply that added this destroyed the pool and both
  # accounts in it. #374 asked for the decision to be recorded next to the pool
  # either way, so here it is.
  #
  # **The case for leaving it alone, which was real.** Unlike humbugg's pool,
  # this one sets `allow_admin_create_user_only = true` above. #374's harm is
  # two accounts for one address — reproduced on a scratch pool: same address in
  # two casings, two accounts, two distinct subs — and producing it needs a
  # stranger who can register. Here nobody can. A mixed-case sign-in against
  # this pool could only ever fail to authenticate; the person retyped it. So
  # the reachable exposure was an admin typo in `create-user.sh`, and the price
  # of removing it was destroying the only two accounts that exist.
  #
  # **It was replaced anyway, deliberately.** What the pool cost to fix only
  # ever went up, and the thing it would have cost was small and fully
  # recoverable: nothing in the library is keyed on a Cognito `sub` except
  # membership. Measured against the real table before the apply — 458 items,
  # of which 416 nodes, 36 characters and 4 library rows reference no sub at
  # all, and not one S3 key does. Two rows did:
  #
  #     USER#<sub> -> LIB#<lib>   the owner
  #     USER#<sub> -> LIB#lib-smoke
  #
  # The smoke row heals itself on the next deploy — `prod-seed-smoke.py`
  # converges that account and its membership every time. The owner's is one
  # `create-user.sh` run with `STUDIO_LIBRARY` set, which is the step that
  # exists for exactly this. See `docs/POOL_REPLACEMENT.md`.
  #
  # **What this does NOT survive.** The old `USER#<sub>` rows are left behind
  # pointing at subs that no longer exist. They are inert — authorisation reads
  # the caller's own sub — but they are litter, and the runbook deletes them.
  username_configuration {
    case_sensitive = false
  }

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true
  }

  # OPTIONAL, never ON. ON forces enrolment at the next sign-in for every
  # existing account and strands anyone who cannot complete it; OPTIONAL is
  # inert until a user enrols. Managed Login's hosted pages render both the
  # enrolment and the challenge, so this is reachable surface rather than a
  # dormant setting — studio has no in-app screen for either and needs none.
  # No SMS MFA: it needs an SNS setup and is the weaker factor.
  mfa_configuration = "OPTIONAL"

  software_token_mfa_configuration {
    enabled = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = var.tags
}

resource "aws_cognito_user_pool_client" "main" {
  name         = "${var.name}-web"
  user_pool_id = aws_cognito_user_pool.main.id

  # Secretless: the client id ships in a static bundle, so a secret would be
  # public anyway. SRP never puts the password on the wire, and the browser's
  # code flow is protected by PKCE instead.
  generate_secret = false

  allowed_oauth_flows_user_pool_client = true

  # **No `implicit`.** It returns tokens in the URL fragment — browser history,
  # referrers, server logs — with no PKCE and no exchange step, and OAuth 2.1
  # removes it. With the managed-login domain below, `/oauth2/authorize` is live
  # surface on a client whose id ships in a public bundle, so `code` is the only
  # grant. Cognito has no server-side "require PKCE" toggle: the SPA's PKCE test
  # (`frontend/src/auth/oauth.test.ts`) is what keeps the challenge from
  # silently disappearing.
  allowed_oauth_flows  = ["code"]
  allowed_oauth_scopes = ["openid", "email", "profile"]

  # Exact-match, character for character — no wildcard host, path or port. A
  # client with `code` enabled and no matching entry here fails on the redirect,
  # not at apply time, so register the URL before the app redirects to it.
  callback_urls = var.callback_urls
  logout_urls   = var.logout_urls

  supported_identity_providers = ["COGNITO"]

  # **BOTH OF THESE STAY, AND ROTATION MUST NOT BE ADDED.**
  #
  # `studio login` is a shipped CLI with no browser
  # (`pipeline/src/studio_pipeline/adapters/auth.py`): it signs in with
  # `InitiateAuth` USER_SRP_AUTH and renews with `InitiateAuth`
  # REFRESH_TOKEN_AUTH. `scripts/dev-token.py` and the prod smoke test take the
  # same two flows. Dropping either breaks all three.
  #
  # Scout's copy of this module drops `ALLOW_REFRESH_TOKEN_AUTH` and enables
  # `refresh_token_rotation`, and copying that here does not merely change a
  # policy — Cognito REJECTS rotation alongside `ALLOW_REFRESH_TOKEN_AUTH`, at
  # apply time, in a service-side validation `terraform validate` cannot see.
  # So there is no half-measure: rotation for studio means moving the CLI onto
  # `POST /oauth2/token` first. Until then, do not add it.
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  prevent_user_existence_errors = "ENABLED"

  # Without this a refresh token outlives sign-out and stays usable until it
  # expires. The SPA's sign-out leg calls the hosted `/logout`, which revokes.
  enable_token_revocation = true

  access_token_validity  = 8
  id_token_validity      = 8
  refresh_token_validity = 30
  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }
}

# Cognito's default branding for the managed login (v2) pages. No exported
# console JSON yet — colours can come later by swapping this for `settings`.
resource "aws_cognito_managed_login_branding" "main" {
  user_pool_id                = aws_cognito_user_pool.main.id
  client_id                   = aws_cognito_user_pool_client.main.id
  use_cognito_provided_values = true
}

# THE HOSTED SIGN-IN DOMAIN, IN EITHER OF ITS TWO FORMS.
#
# `envs/prod` passes `auth_domain` — a custom host on the shared wildcard
# certificate, fronted by a Cognito-managed CloudFront distribution the alias
# records below point at. `envs/dev` passes `auth_domain_prefix` instead and
# gets `<prefix>.auth.<region>.amazoncognito.com`: a per-machine stack has no
# certificate and no DNS of its own, and a custom domain would add ~15 minutes
# to every apply and every destroy to prove nothing.
#
# **Branding must exist before the domain.** A managed-login (v2) domain with
# no branding style serves "Login pages unavailable. Please contact an
# administrator." — an outage, not a fallback — so the depends_on edge is
# load-bearing: never let Terraform order the domain first.
resource "aws_cognito_user_pool_domain" "main" {
  domain                = var.auth_domain != "" ? var.auth_domain : var.auth_domain_prefix
  user_pool_id          = aws_cognito_user_pool.main.id
  certificate_arn       = var.auth_domain != "" ? var.auth_certificate_arn : null
  managed_login_version = 2

  lifecycle {
    # Exactly one form. Terraform variable validation cannot see a sibling
    # variable, so the either/or lives here, where both are in scope.
    precondition {
      condition     = (var.auth_domain != "") != (var.auth_domain_prefix != "")
      error_message = "Set exactly one of auth_domain (a custom host) or auth_domain_prefix (a default Cognito domain)."
    }

    # A custom host needs a us-east-1 certificate covering it and a zone to put
    # the alias records in. Missing either, the apply fails ~15 minutes in.
    precondition {
      condition     = var.auth_domain == "" || (var.auth_certificate_arn != "" && var.route53_zone_id != "")
      error_message = "auth_domain requires both auth_certificate_arn and route53_zone_id."
    }
  }

  depends_on = [aws_cognito_managed_login_branding.main]
}

# Cognito fronts the custom domain with its own CloudFront distribution; these
# alias records point the auth host at it. Empty in the default-domain case,
# where Cognito owns the DNS.
resource "aws_route53_record" "auth" {
  for_each = toset(var.auth_domain != "" ? ["A", "AAAA"] : [])

  zone_id = var.route53_zone_id
  name    = var.auth_domain
  type    = each.value

  alias {
    name                   = aws_cognito_user_pool_domain.main.cloudfront_distribution
    zone_id                = aws_cognito_user_pool_domain.main.cloudfront_distribution_zone_id
    evaluate_target_health = false
  }
}

# For the `<prefix>.auth.<region>.amazoncognito.com` host that `outputs.tf`
# composes. Unused in the custom-domain case, and free either way.
data "aws_region" "current" {}
