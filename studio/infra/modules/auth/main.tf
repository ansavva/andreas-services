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

  # **Case-insensitive email usernames — and this argument REPLACES THE POOL.**
  #
  # AWS accepts `username_configuration` only at pool creation, so the provider
  # marks it ForceNew: the apply that added this destroyed the pool and both
  # accounts in it. #374 asked for the decision to be recorded next to the pool
  # either way, so here it is.
  #
  # **The case for leaving it alone, which was real.** Unlike humbugg's pool,
  # this one sets `allow_admin_create_user_only = true` above. #374's harm is
  # two accounts for one address — reproduced on a scratch pool: same address in
  # two casings, two accounts, two distinct subs — and producing it needs a
  # stranger who can register. Here nobody can. A mixed-case sign-in against
  # this pool could only ever fail to authenticate; the person retyped it. So
  # the reachable exposure was an admin typo in `create-user.sh`, and the price
  # of removing it was destroying the only two accounts that exist.
  #
  # **It was replaced anyway, deliberately.** What the pool cost to fix only
  # ever went up, and the thing it would have cost was small and fully
  # recoverable: nothing in the library is keyed on a Cognito `sub` except
  # membership. Measured against the real table before the apply — 458 items,
  # of which 416 nodes, 36 characters and 4 library rows reference no sub at
  # all, and not one S3 key does. Two rows did:
  #
  #     USER#<sub> -> LIB#<lib>   the owner
  #     USER#<sub> -> LIB#lib-smoke
  #
  # The smoke row heals itself on the next deploy — `prod-seed-smoke.py`
  # converges that account and its membership every time. The owner's is one
  # `create-user.sh` run with `STUDIO_LIBRARY` set, which is the step that
  # exists for exactly this. See `docs/POOL_REPLACEMENT.md`.
  #
  # **What this does NOT survive.** The old `USER#<sub>` rows are left behind
  # pointing at subs that no longer exist. They are inert — authorisation reads
  # the caller's own sub — but they are litter, and the runbook deletes them.
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
