# Cognito user pool backing the studio app.
#
# There is no public sign-up and there is not meant to be one: this is a private
# viewer over a private bucket, so accounts are created out of band with
# `studio/scripts/create-user.sh` and `allow_admin_create_user_only` is what
# makes that the only route in. The SPA signs in with SRP through Amplify Auth
# and the API Gateway Cognito authorizer validates the access token.
resource "aws_cognito_user_pool" "main" {
  name = var.name

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

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

  tags = var.tags
}

resource "aws_cognito_user_pool_client" "main" {
  name         = "${var.name}-web"
  user_pool_id = aws_cognito_user_pool.main.id

  # Secretless: the client id ships in a static bundle, so a secret would be
  # public anyway. SRP never puts the password on the wire.
  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

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
