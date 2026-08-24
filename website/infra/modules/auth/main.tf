# Cognito user pool backing the admin dashboard. Single admin user, provisioned
# via `aws cognito-idp admin-create-user` (no public self-signup). The frontend
# authenticates server-side with USER_PASSWORD_AUTH and stores the ID token in a
# session cookie; the API Gateway Cognito authorizer validates it on admin calls.
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

  tags = var.tags
}

resource "aws_cognito_user_pool_client" "main" {
  name         = "${var.name}-web"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false

  # Server-side login (no hosted UI): USER_PASSWORD_AUTH is enough.
  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
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
