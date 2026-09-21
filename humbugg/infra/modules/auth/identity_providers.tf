# Social sign-in: Google, Facebook, Apple and LinkedIn as identity providers on
# the pool. Managed Login renders a button per provider the client lists in
# `supported_identity_providers`, above the password form — the branding
# document's `authMethodOrder` already puts FEDERATED first — so the app needs
# no code for this: the hosted page grows buttons, the callback is unchanged.
#
# **Every provider is optional, gated on its credentials being set.** A dev
# stack applies with none and gets the password form it has today; a developer
# who registers one machine's callback with Google gets Google. Prod passes all
# four from GitHub secrets. Each gate is a `count` on a VARIABLE, never on a
# resource attribute — a count on an attribute cannot be resolved at plan time
# and failed a prod deploy in studio.
#
# Every provider redirects back to `https://<auth host>/oauth2/idpresponse`,
# and that exact URL must be registered on the provider's side by hand —
# `docs/auth-social-login.md` lists where, per provider and per stack.
#
# `email_verified` IS mapped from the providers that emit the claim — Google,
# Apple, LinkedIn — and not from Facebook, which has none. Measured, not
# assumed: an unmapped `email_verified` reaches the pre-sign-up trigger as
# Cognito's own placeholder `false` for every federated user, indistinguishable
# from a provider saying so, and the first live Google sign-in was refused on
# it. Mapped, the trigger sees the provider's real claim and refuses only an
# explicit `false` from a provider that carries one (`pre_sign_up.tf` names
# those in its environment). The cost accepted: a mapped attribute is
# rewritten from the provider on every sign-in, so a provider that later says
# `false` un-verifies the address — which is the truthful state.

locals {
  google_enabled   = var.google_client_id != ""
  facebook_enabled = var.facebook_app_id != ""
  apple_enabled    = var.apple_services_id != ""
  linkedin_enabled = var.linkedin_client_id != ""

  # The declared names, in the order the buttons should read. Composed from the
  # variables rather than the resources so the client and the trigger's
  # environment can reference it without a cycle through the pool.
  identity_provider_names = compact([
    local.google_enabled ? "Google" : "",
    local.apple_enabled ? "SignInWithApple" : "",
    local.facebook_enabled ? "Facebook" : "",
    local.linkedin_enabled ? "LinkedIn" : "",
  ])

  # The subset whose `email_verified` below is the provider's own claim.
  email_verified_provider_names = compact([
    local.google_enabled ? "Google" : "",
    local.apple_enabled ? "SignInWithApple" : "",
    local.linkedin_enabled ? "LinkedIn" : "",
  ])
}

resource "aws_cognito_identity_provider" "google" {
  count = local.google_enabled ? 1 : 0

  user_pool_id  = aws_cognito_user_pool.main.id
  provider_name = "Google"
  provider_type = "Google"

  provider_details = {
    client_id        = var.google_client_id
    client_secret    = var.google_client_secret
    authorize_scopes = "openid email profile"
  }

  attribute_mapping = {
    username         = "sub"
    "custom:idp_sub" = "sub"
    email            = "email"
    email_verified   = "email_verified"
    given_name       = "given_name"
    family_name      = "family_name"
  }

  # Cognito fills in the OAuth endpoints for a Google provider and reports them
  # back; the provider would otherwise plan a rewrite of the map on every run.
  lifecycle {
    ignore_changes = [
      provider_details["attributes_url"],
      provider_details["attributes_url_add_attributes"],
      provider_details["authorize_url"],
      provider_details["oidc_issuer"],
      provider_details["token_request_method"],
      provider_details["token_url"],
    ]
  }
}

resource "aws_cognito_identity_provider" "facebook" {
  count = local.facebook_enabled ? 1 : 0

  user_pool_id  = aws_cognito_user_pool.main.id
  provider_name = "Facebook"
  provider_type = "Facebook"

  provider_details = {
    client_id        = var.facebook_app_id
    client_secret    = var.facebook_app_secret
    authorize_scopes = "public_profile,email"
    # No `api_version`: Cognito picks a current Graph API version and reports
    # it back, ignored below. Pinning one here is pinning a date Meta retires.
  }

  # Facebook's Graph field names, not OIDC's.
  attribute_mapping = {
    username         = "id"
    "custom:idp_sub" = "id"
    email            = "email"
    given_name       = "first_name"
    family_name      = "last_name"
  }

  lifecycle {
    ignore_changes = [
      provider_details["api_version"],
      provider_details["attributes_url"],
      provider_details["attributes_url_add_attributes"],
      provider_details["authorize_url"],
      provider_details["token_request_method"],
      provider_details["token_url"],
    ]
  }
}

# App Store Review Guideline 4.8: an iOS app that offers any third-party
# sign-in must offer Sign in with Apple. `humbugg/app` exists to ship to the
# stores, so this is not optional once Google or Facebook is on.
#
# Apple hands the name over ONCE, on first authorization, and never again; a
# user who revokes and re-authorizes arrives nameless. And Apple may hand over a
# relay address (`@privaterelay.appleid.com`) instead of the real one — mail to
# it bounces unless the sending domain is registered with Apple's Private Email
# Relay Service. `docs/auth-social-login.md`.
resource "aws_cognito_identity_provider" "apple" {
  count = local.apple_enabled ? 1 : 0

  user_pool_id  = aws_cognito_user_pool.main.id
  provider_name = "SignInWithApple"
  provider_type = "SignInWithApple"

  provider_details = {
    client_id        = var.apple_services_id
    team_id          = var.apple_team_id
    key_id           = var.apple_key_id
    private_key      = var.apple_private_key
    authorize_scopes = "email name"
  }

  attribute_mapping = {
    username         = "sub"
    "custom:idp_sub" = "sub"
    email            = "email"
    email_verified   = "email_verified"
    given_name       = "firstName"
    family_name      = "lastName"
  }

  lifecycle {
    ignore_changes = [
      provider_details["attributes_url"],
      provider_details["attributes_url_add_attributes"],
      provider_details["authorize_url"],
      provider_details["oidc_issuer"],
      provider_details["token_request_method"],
      provider_details["token_url"],
    ]
  }
}

# LinkedIn has no native Cognito type; it is "Sign In with LinkedIn using
# OpenID Connect" wired as a generic OIDC provider. Endpoints are spelled out
# rather than discovered so a change to LinkedIn's discovery document is a
# diff here, not a silent outage.
resource "aws_cognito_identity_provider" "linkedin" {
  count = local.linkedin_enabled ? 1 : 0

  user_pool_id  = aws_cognito_user_pool.main.id
  provider_name = "LinkedIn"
  provider_type = "OIDC"

  provider_details = {
    client_id                 = var.linkedin_client_id
    client_secret             = var.linkedin_client_secret
    authorize_scopes          = "openid profile email"
    oidc_issuer               = "https://www.linkedin.com/oauth"
    authorize_url             = "https://www.linkedin.com/oauth/v2/authorization"
    token_url                 = "https://www.linkedin.com/oauth/v2/accessToken"
    attributes_url            = "https://api.linkedin.com/v2/userinfo"
    jwks_uri                  = "https://www.linkedin.com/oauth/openid/jwks"
    attributes_request_method = "GET"
  }

  attribute_mapping = {
    username         = "sub"
    "custom:idp_sub" = "sub"
    email            = "email"
    email_verified   = "email_verified"
    given_name       = "given_name"
    family_name      = "family_name"
  }

  lifecycle {
    ignore_changes = [
      provider_details["attributes_url_add_attributes"],
    ]
  }
}
