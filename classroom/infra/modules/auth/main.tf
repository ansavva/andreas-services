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

# CLASSROOM'S BRAND ON THE HOSTED PAGES.
#
# The sign-in, reset, forced-first-password and TOTP screens are Cognito's, so
# they cannot load `app.css`. This is the only way to stop a teacher meeting a
# stock AWS form on the way into a page that looks nothing like it.
#
# A branding record also has to EXIST for a `managed_login_version = 2` domain
# to serve anything at all — see the domain below — so this resource is
# load-bearing twice over.
#
# `managed-login-settings.json` IS GENERATED, from the design system's
# `theme.css` plus `frontend/src/styles/app.css`, via `npm run brand` in
# `classroom/frontend`; `npm run brand:check` gates the two against drift on
# every PR. The stylesheets are the only source — the derived button states are
# live `color-mix()` blends with no hex to copy, so the tool re-implements the
# blend rather than keeping a second table of colours.
#
# NO ASSETS: classroom has no logo, so `form.logo` stays disabled and Cognito's
# own illustrations stay off. Adding one is ForceNew on this resource, which
# briefly leaves the domain without a style — so it is a deliberate act, not a
# drive-by.
resource "aws_cognito_managed_login_branding" "main" {
  user_pool_id = aws_cognito_user_pool.main.id
  client_id    = aws_cognito_user_pool_client.main.id

  settings = file("${path.module}/managed-login-settings.json")
}

# Managed Login hosts sign-in, password reset, forced first-password change and
# TOTP enrolment, so this service writes none of those screens.
#
# Two shapes, and which one is in force is decided entirely by which variable
# the environment set. `envs/prod` gives a custom host on the shared wildcard
# certificate; `envs/dev` gives a prefix and takes Cognito's own domain. The
# preconditions are what stop a half-configured third shape: a custom domain
# with no certificate applies for several minutes and then fails.
resource "aws_cognito_user_pool_domain" "main" {
  domain          = var.auth_domain != "" ? var.auth_domain : var.auth_domain_prefix
  user_pool_id    = aws_cognito_user_pool.main.id
  certificate_arn = var.auth_domain != "" ? var.auth_certificate_arn : null

  # Version 2 is the styleable Managed Login. Version 1 is the old hosted UI,
  # which ignores the branding record entirely — so this line and the resource
  # above only work as a pair.
  managed_login_version = 2

  lifecycle {
    precondition {
      condition     = (var.auth_domain != "") != (var.auth_domain_prefix != "")
      error_message = "Set exactly one of auth_domain (a custom host) or auth_domain_prefix (a default Cognito domain)."
    }
    precondition {
      condition     = var.auth_domain == "" || (var.auth_certificate_arn != "" && var.route53_zone_id != "")
      error_message = "auth_domain also requires auth_certificate_arn and route53_zone_id."
    }
  }

  # **Branding must exist before the domain.** A managed-login (v2) domain with
  # no branding style serves "Login pages unavailable. Please contact an
  # administrator." — an outage, not a fallback. Never let Terraform order the
  # domain first.
  depends_on = [aws_cognito_managed_login_branding.main]
}

# A Cognito custom domain is a CloudFront distribution Cognito owns, so it needs
# an alias record pointing at it. The default-domain case resolves under
# `amazoncognito.com` and has nothing to publish, hence the count.
resource "aws_route53_record" "auth" {
  count = var.auth_domain != "" ? 1 : 0

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

# The count above changed this resource's ADDRESS, not the record itself.
# Without this, prod's next apply destroys and recreates the auth A record —
# a window in which classroom-auth.andreas.services does not resolve and
# nobody can sign in. Terraform ignores it where the old address never
# existed, which is every dev stack.
moved {
  from = aws_route53_record.auth
  to   = aws_route53_record.auth[0]
}

# For the `<prefix>.auth.<region>.amazoncognito.com` host `outputs.tf` composes.
# Unused in the custom-domain case, and free either way.
data "aws_region" "current" {}
