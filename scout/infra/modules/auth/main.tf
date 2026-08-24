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
  # user enrols. Scout's in-app sign-in form has no enrolment screen and this PR
  # does not add one, so the setting is dormant — it becomes reachable for free
  # when Managed Login lands (#466), which renders both enrolment and challenge.
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
  # removes it. It was enabled here and driven by nothing: the SPA signs in with
  # `amazon-cognito-identity-js`'s `authenticateUser`, which is SRP.
  #
  # It was inert only by accident. Scout declares no `aws_cognito_user_pool_domain`,
  # so `/oauth2/authorize` does not resolve and the grant could not be reached. The
  # day anyone adds a domain — including the one that comes with adopting Managed
  # Login, #363 — it would have become live surface on a client whose id ships in a
  # public bundle. Removing it now costs nothing.
  allowed_oauth_flows  = ["code"]
  allowed_oauth_scopes = ["openid", "email", "profile"]

  callback_urls = var.callback_urls
  logout_urls   = var.logout_urls

  supported_identity_providers = ["COGNITO"]

  # **No `ALLOW_USER_PASSWORD_AUTH`.** It puts a raw password in an `InitiateAuth`
  # call, and it is the flow every credential-stuffing script targets. Nothing in
  # `scout/` ever called it — SRP never puts the password on the wire — so this is
  # deleting attack surface, not a capability.
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  prevent_user_existence_errors = "ENABLED"

  # Without this a refresh token outlives sign-out and stays usable until it
  # expires. It matters most once there is a `/logout` leg to call (#466) — but
  # set after the fact that leg would have nothing to revoke.
  enable_token_revocation = true

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
