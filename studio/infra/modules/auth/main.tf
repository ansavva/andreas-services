# Cognito user pool backing the studio app.
#
# **Sign-up is self-service and invite-gated.** The pool accepts `SignUp` from
# anyone — `studio signup` from a terminal, or the SPA's sign-up page — and the
# pre-sign-up trigger at the bottom of this file refuses every one that does
# not carry the invite code in `ClientMetadata`. It used to be admin-create-only
# with `scripts/create-user.sh` as the only route in; that script still works
# and is now the exception rather than the rule. The gate exists because every
# account that signs in can submit a generation billed to the one provider
# token the API holds — "anyone with an email" is not an acceptable population.
#
# The SPA signs in through Cognito Managed Login (the hosted pages on the
# domain further down) and the API Gateway Cognito authorizer validates the ID
# token. **Managed Login's own sign-up page is not a route in**: it has no field
# for the code, so the trigger refuses it with a message naming where to go.
#
# **The CLI does not use Managed Login.** `studio login` authenticates with SRP
# against `InitiateAuth` and holds no browser — which is why the client below
# keeps `ALLOW_USER_SRP_AUTH` and `ALLOW_REFRESH_TOKEN_AUTH`, and why
# refresh-token rotation is not enabled here. Read the comment on
# `explicit_auth_flows` before changing either.
resource "aws_cognito_user_pool" "main" {
  name = var.name

  # Self sign-up on; the trigger below is what keeps the pool closed. An
  # administrator can still create an account (`scripts/create-user.sh`).
  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  lambda_config {
    pre_sign_up = aws_lambda_function.signup_gate.arn
  }

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # **Case-insensitive email usernames — and this argument REPLACES THE POOL.**
  #
  # AWS accepts `username_configuration` only at pool creation, so the provider
  # marks it ForceNew: the apply that added this destroyed the pool and both
  # accounts in it. The decision is recorded next to the pool, so here it is.
  #
  # **The case for leaving it alone, which was real at the time.** This pool
  # was then admin-create-only. The harm of a case-sensitive username is two
  # accounts for one address — reproduced on a scratch pool: same address in
  # two casings, two accounts, two distinct subs — and producing it needs a
  # stranger who can register. Then nobody could. A mixed-case sign-in against
  # this pool could only ever fail to authenticate; the person retyped it. So
  # the reachable exposure was an admin typo in `create-user.sh`, and the price
  # of removing it was destroying the only two accounts that exist.
  #
  # Now that the pool accepts self sign-up, this setting is what stops exactly
  # that two-accounts-one-address outcome — so what was a judgement call is
  # load-bearing.
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
  # pointing at subs the new pool does not have. They are inert — authorisation reads
  # the caller's own sub — but they are litter, and the runbook deletes them.
  username_configuration {
    case_sensitive = false
  }

  # The address IS the username (`username_attributes` above), so changing it
  # is changing what the person signs in with — for the SPA and for
  # `studio login` alike. This keeps the OLD address in force until the new one
  # proves it can receive mail: `UpdateUserAttributes` on `email` sends a code
  # to the new address and changes nothing, and `VerifyUserAttribute` with that
  # code is what swaps it. Without this the swap is immediate, `email_verified`
  # drops to false, and a typo in the new address is a locked-out account with
  # no recovery route, because recovery below goes to the verified email.
  # The SPA drives both calls itself — `frontend/src/auth/account.ts` — on the
  # `aws.cognito.signin.user.admin` scope the client grants further down.
  user_attribute_update_settings {
    attributes_require_verification_before_update = ["email"]
  }

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true
  }

  # OPTIONAL, never ON. ON forces enrolment at the next sign-in for every
  # existing account and strands anyone who cannot complete it; OPTIONAL is
  # inert until a user enrols. Managed Login's hosted pages render both the
  # enrolment and the challenge, so this is reachable surface rather than a
  # dormant setting — studio has no in-app screen for either and needs none.
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

  # Secretless: the client id ships in a static bundle, so a secret would be
  # public anyway. SRP never puts the password on the wire, and the browser's
  # code flow is protected by PKCE instead.
  generate_secret = false

  allowed_oauth_flows_user_pool_client = true

  # **No `implicit`.** It returns tokens in the URL fragment — browser history,
  # referrers, server logs — with no PKCE and no exchange step, and OAuth 2.1
  # removes it. With the managed-login domain below, `/oauth2/authorize` is live
  # surface on a client whose id ships in a public bundle, so `code` is the only
  # grant. Cognito has no server-side "require PKCE" toggle: the SPA's PKCE test
  # (`frontend/src/auth/oauth.test.ts`) is what keeps the challenge from
  # silently disappearing.
  allowed_oauth_flows = ["code"]

  # `aws.cognito.signin.user.admin` is what lets an ACCESS token call the
  # self-service user APIs — `UpdateUserAttributes`, `VerifyUserAttribute` —
  # which is how the app changes the signed-in address. It is scoped to the
  # token holder's own record; "admin" is Cognito's name, not a grant over the
  # pool. Requested by name in the authorize leg (`frontend/src/auth/oauth.ts`):
  # a token issued before this scope was granted does not carry it, and a
  # refresh keeps the original grant, so those sessions have to sign in again.
  allowed_oauth_scopes = ["openid", "email", "profile", "aws.cognito.signin.user.admin"]

  # Exact-match, character for character — no wildcard host, path or port. A
  # client with `code` enabled and no matching entry here fails on the redirect,
  # not at apply time, so register the URL before the app redirects to it.
  callback_urls = var.callback_urls
  logout_urls   = var.logout_urls

  supported_identity_providers = ["COGNITO"]

  # **BOTH OF THESE STAY, AND ROTATION MUST NOT BE ADDED.**
  #
  # `studio login` is a shipped CLI with no browser
  # (`pipeline/src/studio_pipeline/adapters/auth.py`): it signs in with
  # `InitiateAuth` USER_SRP_AUTH and renews with `InitiateAuth`
  # REFRESH_TOKEN_AUTH. `scripts/dev-token.py` and the prod smoke test take the
  # same two flows. Dropping either breaks all three.
  #
  # A sibling copy of this module once dropped `ALLOW_REFRESH_TOKEN_AUTH` and
  # enabled `refresh_token_rotation`; copying that here does not merely change a
  # policy — Cognito REJECTS rotation alongside `ALLOW_REFRESH_TOKEN_AUTH`, at
  # apply time, in a service-side validation `terraform validate` cannot see.
  # So there is no half-measure: rotation for studio means moving the CLI onto
  # `POST /oauth2/token` first. Until then, do not add it.
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  prevent_user_existence_errors = "ENABLED"

  # Without this a refresh token outlives sign-out and stays usable until it
  # expires. The SPA's sign-out leg calls the hosted `/logout`, which revokes.
  enable_token_revocation = true

  access_token_validity  = 8
  id_token_validity      = 8
  refresh_token_validity = 30
  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }
}

# Studio's colours on the hosted pages. A branding record also has to EXIST for
# a `managed_login_version = 2` domain to serve anything — see the domain
# below — so this resource is load-bearing twice over.
#
# `managed-login-settings.json` IS GENERATED, from `frontend/src/styles/app.css`
# via `npm run brand` in `studio/frontend`; `npm run brand:check` gates the two
# against drift on every PR. The stylesheet is the only source — the derived
# states are live `color-mix()` blends with no hex to copy, so the tool
# re-implements the blend rather than keeping a second table of colours.
#
# NO ASSETS: studio has no logo yet, so `form.logo` stays disabled. When there
# is one, it lands here as an `asset` block — humbugg's auth module has the
# shape. Note that adding one is ForceNew on this resource, which briefly leaves
# the domain without a style.
resource "aws_cognito_managed_login_branding" "main" {
  user_pool_id = aws_cognito_user_pool.main.id
  client_id    = aws_cognito_user_pool_client.main.id

  settings = file("${path.module}/managed-login-settings.json")
}

# THE HOSTED SIGN-IN DOMAIN, IN EITHER OF ITS TWO FORMS.
#
# `envs/prod` passes `auth_domain` — a custom host on the shared wildcard
# certificate, fronted by a Cognito-managed CloudFront distribution the alias
# records below point at. `envs/dev` passes `auth_domain_prefix` instead and
# gets `<prefix>.auth.<region>.amazoncognito.com`: a per-machine stack has no
# certificate and no DNS of its own, and a custom domain would add ~15 minutes
# to every apply and every destroy to prove nothing.
#
# **Branding must exist before the domain.** A managed-login (v2) domain with
# no branding style serves "Login pages unavailable. Please contact an
# administrator." — an outage, not a fallback — so the depends_on edge is
# load-bearing: never let Terraform order the domain first.
resource "aws_cognito_user_pool_domain" "main" {
  domain                = var.auth_domain != "" ? var.auth_domain : var.auth_domain_prefix
  user_pool_id          = aws_cognito_user_pool.main.id
  certificate_arn       = var.auth_domain != "" ? var.auth_certificate_arn : null
  managed_login_version = 2

  lifecycle {
    # Exactly one form. Terraform variable validation cannot see a sibling
    # variable, so the either/or lives here, where both are in scope.
    precondition {
      condition     = (var.auth_domain != "") != (var.auth_domain_prefix != "")
      error_message = "Set exactly one of auth_domain (a custom host) or auth_domain_prefix (a default Cognito domain)."
    }

    # A custom host needs a us-east-1 certificate covering it and a zone to put
    # the alias records in. Missing either, the apply fails ~15 minutes in.
    precondition {
      condition     = var.auth_domain == "" || (var.auth_certificate_arn != "" && var.route53_zone_id != "")
      error_message = "auth_domain requires both auth_certificate_arn and route53_zone_id."
    }
  }

  depends_on = [aws_cognito_managed_login_branding.main]
}

# Cognito fronts the custom domain with its own CloudFront distribution; these
# alias records point the auth host at it. Empty in the default-domain case,
# where Cognito owns the DNS.
resource "aws_route53_record" "auth" {
  for_each = toset(var.auth_domain != "" ? ["A", "AAAA"] : [])

  zone_id = var.route53_zone_id
  name    = var.auth_domain
  type    = each.value

  alias {
    name                   = aws_cognito_user_pool_domain.main.cloudfront_distribution
    zone_id                = aws_cognito_user_pool_domain.main.cloudfront_distribution_zone_id
    evaluate_target_health = false
  }
}

# For the `<prefix>.auth.<region>.amazoncognito.com` host that `outputs.tf`
# composes. Unused in the custom-domain case, and free either way.
data "aws_region" "current" {}

# ---------------------------------------------------------------------------
# The sign-up gate
# ---------------------------------------------------------------------------
#
# A pre-sign-up trigger that refuses any `SignUp` not carrying the invite code
# in `ClientMetadata`. Packaged straight out of the repo as a one-file zip, the
# way `modules/callbacks` packages the hook receiver and for the same reason:
# it imports nothing from `studio_core`, so the per-machine dev pool can carry
# the identical gate without an image build. See the handler's docstring for
# what it checks and why Managed Login's hosted sign-up page cannot pass it.
#
# **Closed by default.** `var.invite_code` empty means the handler refuses
# everyone — a stack applied before the secret was set is a pool nobody can
# join, never one anybody can. The code rides in as a Lambda environment
# variable rather than an SSM parameter: it is one short string this function
# alone reads, and the alternative is an IAM grant, a KMS grant and a cold-start
# fetch for a value Terraform already holds. It is in state either way.
data "archive_file" "signup_gate" {
  type        = "zip"
  source_file = "${path.module}/../../../backend/studio_core/handlers/aws/signup/presignup_handler.py"
  output_path = "${path.module}/.terraform-build/presignup_handler.zip"
}

data "aws_iam_policy_document" "signup_gate_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "signup_gate" {
  name               = "${var.name}-signup-gate-role"
  assume_role_policy = data.aws_iam_policy_document.signup_gate_assume.json
  tags               = var.tags
}

# Logs, and nothing else. It reads one environment variable and compares two
# strings; it cannot reach the pool, the catalog or the bucket.
resource "aws_iam_role_policy" "signup_gate" {
  name = "${var.name}-signup-gate-logs"
  role = aws_iam_role.signup_gate.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      },
    ]
  })
}

resource "aws_lambda_function" "signup_gate" {
  function_name    = "${var.name}-signup-gate"
  role             = aws_iam_role.signup_gate.arn
  runtime          = "python3.12"
  handler          = "presignup_handler.handler"
  filename         = data.archive_file.signup_gate.output_path
  source_code_hash = data.archive_file.signup_gate.output_base64sha256

  # Cognito gives a trigger five seconds; this needs milliseconds.
  timeout     = 5
  memory_size = 128

  environment {
    variables = {
      STUDIO_INVITE_CODE = var.invite_code
    }
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "signup_gate" {
  name              = "/aws/lambda/${aws_lambda_function.signup_gate.function_name}"
  retention_in_days = 14
  tags              = var.tags
}

# Cognito invokes the trigger as the pool, and Lambda has to be told to let it.
# Without this the pool applies cleanly and every sign-up fails with
# "PreSignUp invocation failed due to error AccessDeniedException" — which
# reads like the gate refusing, and is not.
resource "aws_lambda_permission" "signup_gate" {
  statement_id  = "AllowCognitoInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.signup_gate.function_name
  principal     = "cognito-idp.amazonaws.com"
  source_arn    = aws_cognito_user_pool.main.arn
}
