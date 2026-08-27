# Cognito user pool backing the admin dashboard. Single admin user, provisioned
# via `aws cognito-idp admin-create-user` (no public self-signup). Sign-in runs
# on Cognito Managed Login: the www Lambda exchanges the authorization code
# server-side and stores the ID token in a session cookie; the API Gateway
# Cognito authorizer validates it on admin calls.
resource "aws_cognito_user_pool" "main" {
  name = var.name

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # **Case-insensitive email usernames — and this argument REPLACES THE POOL.**
  #
  # `username_configuration` is accepted only at pool creation, so the provider
  # marks it ForceNew: applying it destroys the pool and every account in it.
  # Cheap here for the same reason it is in scout — one admin account, and
  # nothing in `website/` keys on the Cognito `sub`. The session cookie holds an
  # ID token used only as a bearer credential; intake submissions are not
  # user-keyed.
  #
  # The account itself is recreated by the `Create admin user` step in
  # `website-prod.yaml`, but only if `ADMIN_EMAIL` and `ADMIN_PASSWORD` are set.
  # Unset, that step self-skips and the admin console is locked out until
  # `create-admin-user.sh` is run by hand.
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

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # Enrolment and challenge screens ship with the hosted pages; nothing in
  # `website/` has to render them.
  mfa_configuration = "OPTIONAL"
  software_token_mfa_configuration {
    enabled = true
  }

  tags = var.tags
}

resource "aws_cognito_user_pool_client" "main" {
  name         = "${var.name}-web"
  user_pool_id = aws_cognito_user_pool.main.id

  # Confidential client — the code exchange runs in the www Lambda, never a
  # browser. ForceNew: this replaces the client, so the id AND the secret both
  # change. The pool and its accounts are untouched.
  generate_secret = true

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]

  # Exact-match, character for character — a trailing slash is a different URL.
  callback_urls = var.callback_urls
  logout_urls   = var.logout_urls

  # The plaintext flow is retired: nothing calls InitiateAuth any more. SRP and
  # refresh stay because they cost nothing and keep `aws cognito-idp` usable.
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  enable_token_revocation = true

  # No `refresh_token_rotation`: no refresh token is ever stored. The 8h session
  # cookie is the whole session, and its expiry bounces back through hosted
  # authorize.

  prevent_user_existence_errors = "ENABLED"

  access_token_validity  = 8
  id_token_validity      = 8
  refresh_token_validity = 30
  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }
}

# Cognito's own default styling. A managed-login v2 domain with no branding
# record serves "Login pages unavailable" — an outage, not a fallback — so this
# resource must exist before the domain below.
resource "aws_cognito_managed_login_branding" "main" {
  user_pool_id                = aws_cognito_user_pool.main.id
  client_id                   = aws_cognito_user_pool_client.main.id
  use_cognito_provided_values = true
}

resource "aws_cognito_user_pool_domain" "main" {
  domain          = var.auth_domain
  user_pool_id    = aws_cognito_user_pool.main.id
  certificate_arn = var.auth_certificate_arn

  managed_login_version = 2

  depends_on = [aws_cognito_managed_login_branding.main]
}

resource "aws_route53_record" "auth_a" {
  zone_id = var.route53_zone_id
  name    = var.auth_domain
  type    = "A"

  alias {
    name                   = aws_cognito_user_pool_domain.main.cloudfront_distribution
    zone_id                = aws_cognito_user_pool_domain.main.cloudfront_distribution_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "auth_aaaa" {
  zone_id = var.route53_zone_id
  name    = var.auth_domain
  type    = "AAAA"

  alias {
    name                   = aws_cognito_user_pool_domain.main.cloudfront_distribution
    zone_id                = aws_cognito_user_pool_domain.main.cloudfront_distribution_zone_id
    evaluate_target_health = false
  }
}
