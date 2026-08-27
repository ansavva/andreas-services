resource "aws_cognito_user_pool" "main" {
  name = var.name

  # Admin-only: users are provisioned via `aws cognito-idp admin-create-user`,
  # there is no public self-signup.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # **Case-insensitive email usernames — and this argument REPLACES THE POOL.**
  #
  # `username_configuration` is accepted only at pool creation, so the provider
  # marks it ForceNew: applying it destroys the pool and every account in it.
  # Cheap here because scout's pool holds one admin account and **nothing in
  # `scout/` keys on the Cognito `sub`** — sources, runs, events and locations
  # are all keyed on their own ids, so a new pool orphans no data.
  #
  # What it does cost is the admin account. `bootstrap-admin` in
  # `scout-prod.yaml` recreates it on the next deploy, but only if
  # `SCOUT_ADMIN_PASSWORD` is set in the `scout-production` environment — with
  # the secret unset that job self-skips and the admin console is locked out
  # until someone runs `create-admin-user.sh` by hand.
  username_configuration {
    case_sensitive = false
  }

  # Cognito applies this when a password is *set*, so raising the floor stops new
  # weak passwords and changes nothing retroactively: an account already under 12
  # characters stays there until its next reset. Length beats charset composition,
  # so `require_symbols` stays false — forcing symbols mostly forces `Password1!`.
  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true
  }

  # OPTIONAL, never ON. ON forces enrolment at the next sign-in for every existing
  # account and strands anyone who cannot complete it; OPTIONAL is inert until a
  # user enrols. Managed Login's hosted pages render both enrolment and
  # challenge, so the setting is reachable — no in-app screens needed.
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

  callback_urls = var.callback_urls
  logout_urls   = var.logout_urls

  supported_identity_providers = ["COGNITO"]

  # **No `ALLOW_USER_PASSWORD_AUTH`.** It puts a raw password in an `InitiateAuth`
  # call, and it is the flow every credential-stuffing script targets. Nothing in
  # `scout/` ever called it — SRP never puts the password on the wire — so this is
  # deleting attack surface, not a capability.
  #
  # **No `ALLOW_REFRESH_TOKEN_AUTH` either.** With `refresh_token_rotation`
  # enabled below, Cognito rejects the pair at apply time — service-side
  # validation `terraform validate` cannot see, so never re-add it here.
  # Refresh still works: the SPA refreshes at the token endpoint, which these
  # flags do not gate.
  #
  # SRP is what is left, and the hosted pages do not use it either — Managed
  # Login authenticates server-side, not through the client's explicit flows.
  # It is kept as the one direct-auth flow available to `InitiateAuth` for
  # admin and bootstrap use. Nothing in `scout/` calls it today.
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
  ]

  prevent_user_existence_errors = "ENABLED"

  # Without this a refresh token outlives sign-out and stays usable until it
  # expires. The SPA's sign-out leg calls the hosted `/logout`, which revokes.
  enable_token_revocation = true

  # Every refresh answers with a NEW refresh token and retires the old one, so
  # a stolen token dies at the next legitimate refresh. The grace window
  # absorbs two tabs refreshing concurrently — the SPA also single-flights
  # refreshes (`frontend/src/auth/oauth.ts`), so grace is belt-and-braces.
  refresh_token_rotation {
    feature                    = "ENABLED"
    retry_grace_period_seconds = 30
  }

  # Pinned to the values scout was already taking implicitly, so no session
  # changes and nobody is signed out. Unpinned they are Cognito's defaults, which
  # a provider or service default change could move without ever showing a diff.
  access_token_validity  = 1
  id_token_validity      = 1
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

# **Branding must exist before the domain.** A managed-login (v2) domain with
# no branding style serves "Login pages unavailable. Please contact an
# administrator." — an outage, not a fallback — so the depends_on edge is
# load-bearing: never let Terraform order the domain first.
resource "aws_cognito_user_pool_domain" "main" {
  domain                = var.auth_domain
  user_pool_id          = aws_cognito_user_pool.main.id
  certificate_arn       = var.auth_certificate_arn
  managed_login_version = 2

  depends_on = [aws_cognito_managed_login_branding.main]
}

# Cognito fronts the custom domain with its own CloudFront distribution; these
# alias records point the auth host at it.
resource "aws_route53_record" "auth" {
  for_each = toset(["A", "AAAA"])

  zone_id = var.route53_zone_id
  name    = var.auth_domain
  type    = each.value

  alias {
    name                   = aws_cognito_user_pool_domain.main.cloudfront_distribution
    zone_id                = aws_cognito_user_pool_domain.main.cloudfront_distribution_zone_id
    evaluate_target_health = false
  }
}
