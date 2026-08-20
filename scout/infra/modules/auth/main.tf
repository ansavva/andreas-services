resource "aws_cognito_user_pool" "main" {
  name = var.name

  # Admin-only: users are provisioned via `aws cognito-idp admin-create-user`,
  # there is no public self-signup.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true
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
}
