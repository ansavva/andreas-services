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
  # user enrols. There is nowhere to enrol yet — that arrives with either a
  # settings-screen TOTP flow or Managed Login (#365) — so this is dormant
  # capability, not a live second factor.
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

resource "aws_cognito_user_pool_client" "main" {
  name         = "${var.project}-${var.environment}-app"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false
  callback_urls   = var.callback_urls
  logout_urls     = var.logout_urls

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

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
