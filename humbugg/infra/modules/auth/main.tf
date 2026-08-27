resource "aws_cognito_user_pool" "main" {
  name = "${var.project}-${var.environment}"

  lifecycle {
    precondition {
      condition = (
        var.email_sending_account == "COGNITO_DEFAULT" ||
        (
          var.email_from_address != null &&
          var.email_source_arn != null &&
          var.email_configuration_set != null
        )
      )
      error_message = "DEVELOPER email requires a From address, SES source ARN, and configuration set."
    }
  }

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # **Case-insensitive email usernames — and this argument REPLACES THE POOL.**
  #
  # AWS accepts `username_configuration` only at pool creation, so the provider
  # marks it ForceNew: an apply that adds it destroys the pool and every account
  # in it. That is affordable here for exactly one reason, and it is a fact about
  # today rather than about this design — the pool held **zero** users when this
  # landed, so there was nothing to destroy.
  #
  # It does not stay affordable. Self-signup is open below
  # (`allow_admin_create_user_only = false`), and every humbugg row keys on the
  # Cognito `sub` — profiles, groups, group members, draws, audit events,
  # billing. The first real signup turns this line from free into a data
  # migration, because a new pool mints new subs and orphans all of it.
  #
  # Without this, `Alice@example.com` and `alice@example.com` are two accounts
  # with two subs. Measured, not inferred: creating both casings in a pool
  # configured like this one produced two users.
  username_configuration {
    case_sensitive = false
  }

  # Cognito applies this when a password is *set*, so raising the floor stops new
  # weak passwords and changes nothing retroactively: anyone already under 12
  # characters stays there until their next reset. Length beats charset
  # composition, so `require_symbols` stays false — forcing symbols mostly
  # forces `Password1!`.
  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = false
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true

    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  schema {
    name                = "given_name"
    attribute_data_type = "String"
    required            = false
    mutable             = true

    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  schema {
    name                = "family_name"
    attribute_data_type = "String"
    required            = false
    mutable             = true

    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  email_configuration {
    email_sending_account = var.email_sending_account
    from_email_address = (
      var.email_sending_account == "DEVELOPER" ? var.email_from_address : null
    )
    source_arn = (
      var.email_sending_account == "DEVELOPER" ? var.email_source_arn : null
    )
    configuration_set = (
      var.email_sending_account == "DEVELOPER" ? var.email_configuration_set : null
    )
  }

  # OPTIONAL, never ON. ON forces enrolment at the next sign-in for every existing
  # account and strands anyone who cannot complete it; OPTIONAL is inert until a
  # user enrols. Enrolment now exists: the Managed Login pages below carry the
  # TOTP flow, which is what #365 unlocked.
  mfa_configuration = "OPTIONAL"

  software_token_mfa_configuration {
    enabled = true
  }

  user_pool_add_ons {
    advanced_security_mode = "OFF"
  }

  tags = var.tags

  admin_create_user_config {
    allow_admin_create_user_only = false
  }
}

# The region is only ever needed to spell out a DEFAULT Cognito domain's host,
# which the module has no other way to learn.
data "aws_region" "current" {}

resource "aws_cognito_user_pool_client" "main" {
  name         = "${var.project}-${var.environment}-app"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false
  callback_urls   = var.callback_urls
  logout_urls     = var.logout_urls

  # Authorization code + PKCE against the Managed Login pages. Without
  # `allowed_oauth_flows_user_pool_client` no /oauth2 endpoint answers at all and
  # `callback_urls` above are inert, so this line is what makes them live.
  # Registration is exact-match: every redirect URI the app can produce, web and
  # custom-scheme alike, has to appear literally in those lists.
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]

  # **`ALLOW_REFRESH_TOKEN_AUTH` must never come back while this block exists.**
  # Cognito rejects the pair at apply time — `terraform validate` and `tflint`
  # both pass on a configuration that cannot apply, so the only warning is a
  # failed deploy. The two changed together in one apply for that reason.
  #
  # SRP survives because it is the last direct-auth flow left for admin and dev
  # tooling — #373's authenticated round trip against a per-machine dev pool
  # signs in that way. The hosted pages do NOT need it: Managed Login talks to
  # the pool server-side and never calls InitiateAuth as this client.
  refresh_token_rotation {
    feature = "ENABLED"
    # A rotated refresh token invalidates its predecessor immediately, so two
    # requests that raced the same expiry would leave one holding a dead token.
    # The grace window lets the loser retry with what it already had.
    retry_grace_period_seconds = 30
  }

  explicit_auth_flows = ["ALLOW_USER_SRP_AUTH"]

  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true
  access_token_validity         = 1
  id_token_validity             = 1
  refresh_token_validity        = 30

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }
}

# Cognito's own palette and copy. A branding record has to EXIST for a
# `managed_login_version = 2` domain to serve anything — see the domain below —
# so this is not the cosmetic step it looks like. Humbugg's colours would
# replace `use_cognito_provided_values` with an exported settings document; that
# is a later change and a strictly optional one.
resource "aws_cognito_managed_login_branding" "main" {
  user_pool_id                = aws_cognito_user_pool.main.id
  client_id                   = aws_cognito_user_pool_client.main.id
  use_cognito_provided_values = true
}

# Where the hosted pages are served from. Exactly one shape at a time: a custom
# domain in prod (a name on Humbugg's own certificate, aliased below), or a
# default `<prefix>.auth.<region>.amazoncognito.com` for the per-machine dev
# stacks — those take the default so a dev stack costs no certificate SAN, no
# DNS record and no ~15-minute apply either way.
#
# `depends_on` is load-bearing, not tidiness: a v2 domain created before its
# branding record serves "Login pages unavailable" to every visitor. That is an
# outage, not a graceful fallback to v1.
resource "aws_cognito_user_pool_domain" "main" {
  domain          = var.auth_domain != null ? var.auth_domain : var.auth_domain_prefix
  user_pool_id    = aws_cognito_user_pool.main.id
  certificate_arn = var.auth_domain != null ? var.auth_certificate_arn : null

  managed_login_version = 2

  depends_on = [aws_cognito_managed_login_branding.main]

  lifecycle {
    precondition {
      condition     = (var.auth_domain == null) != (var.auth_domain_prefix == null)
      error_message = "Set exactly one of auth_domain (a custom domain) or auth_domain_prefix (a default Cognito domain)."
    }

    precondition {
      condition     = var.auth_domain == null || (var.auth_certificate_arn != null && var.route53_zone_id != null)
      error_message = "auth_domain also requires auth_certificate_arn and route53_zone_id."
    }
  }
}

# A Cognito custom domain is a CloudFront distribution Cognito owns, so it needs
# the same A + AAAA alias pair any CloudFront alias does. The default-domain case
# resolves on its own and creates neither.
resource "aws_route53_record" "auth_a" {
  count = var.auth_domain != null ? 1 : 0

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
  count = var.auth_domain != null ? 1 : 0

  zone_id = var.route53_zone_id
  name    = var.auth_domain
  type    = "AAAA"

  alias {
    name                   = aws_cognito_user_pool_domain.main.cloudfront_distribution
    zone_id                = aws_cognito_user_pool_domain.main.cloudfront_distribution_zone_id
    evaluate_target_health = false
  }
}
