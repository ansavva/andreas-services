resource "aws_cognito_user_pool" "main" {
  name = var.name

  # Admin-only. Teachers are provisioned deliberately — this is a small pool of
  # colleagues, not a public sign-up product, and an open pool on a domain that
  # serves pages to minors is not a default worth having.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # Set at creation. `username_configuration` is accepted only when the pool is
  # created, so the provider marks it ForceNew: changing it later destroys the
  # pool and every account in it. It matters here because classroom keys every
  # page on the Cognito `sub` — a new pool would orphan every page ever written.
  username_configuration {
    case_sensitive = false
  }

  # Length beats charset composition, so `require_symbols` stays false: forcing
  # symbols mostly forces `Password1!`.
  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true
  }

  # OPTIONAL, never ON. ON forces enrolment at the next sign-in for every
  # existing account and strands anyone who cannot complete it.
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
  # removes it. `code` is the only grant. Cognito has no server-side "require
  # PKCE" toggle, so the SPA's PKCE test (frontend/src/auth/oauth.test.ts) is
  # what keeps the challenge from silently disappearing.
  allowed_oauth_flows  = ["code"]
  allowed_oauth_scopes = ["openid", "email", "profile"]

  callback_urls = var.callback_urls
  logout_urls   = var.logout_urls

  supported_identity_providers = ["COGNITO"]

  # **No `ALLOW_USER_PASSWORD_AUTH`.** It puts a raw password in an
  # `InitiateAuth` call and is what every credential-stuffing script targets.
  # Nothing in classroom calls it — the browser uses the hosted page, and SRP
  # never puts a password on the wire.
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  # An hour of API access, thirty days before a teacher has to sign in again.
  # Long enough that the app is not asking for a password during a lesson.
  access_token_validity  = 1
  id_token_validity      = 1
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  prevent_user_existence_errors = "ENABLED"
}

# Managed Login hosts sign-in, password reset, forced first-password change and
# TOTP enrolment, so this service writes none of those screens.
resource "aws_cognito_user_pool_domain" "main" {
  domain          = var.auth_domain
  user_pool_id    = aws_cognito_user_pool.main.id
  certificate_arn = var.auth_certificate_arn
}

resource "aws_route53_record" "auth" {
  zone_id = var.route53_zone_id
  name    = var.auth_domain
  type    = "A"

  alias {
    name    = aws_cognito_user_pool_domain.main.cloudfront_distribution
    zone_id = aws_cognito_user_pool_domain.main.cloudfront_distribution_zone_id
    # Cognito's managed distribution has no health check to evaluate.
    evaluate_target_health = false
  }
}
