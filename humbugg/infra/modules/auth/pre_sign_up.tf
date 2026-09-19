# The pre-sign-up trigger: what makes a social sign-in land on the same
# account as the password one. `scripts/auth-trigger/pre-sign-up.mjs` says
# how; this packages it — a zip straight from the file, the webhook relay's
# shape, no build and no ECR — and grants it the six admin calls it makes,
# on this pool only.
#
# Created on every stack, providers or not: it passes native sign-ups through
# untouched, and a dev stack with no provider still exercises the pass-through.
#
# Ordering, because the graph is nearly a cycle: the pool names the function in
# `lambda_config`, so the function cannot depend on the pool. It depends on the
# ROLE only. The role's policy and the invoke permission both name the pool's
# ARN and are created after it, which is fine — Cognito invokes nothing until a
# sign-up happens.

locals {
  pre_sign_up_name = "${var.project}-${var.environment}-auth-pre-sign-up"
}

data "archive_file" "pre_sign_up" {
  type        = "zip"
  source_file = "${path.module}/../../../scripts/auth-trigger/pre-sign-up.mjs"
  output_path = "${path.module}/.terraform-build/pre-sign-up.zip"
}

data "aws_iam_policy_document" "pre_sign_up_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "pre_sign_up" {
  name               = "${local.pre_sign_up_name}-role"
  assume_role_policy = data.aws_iam_policy_document.pre_sign_up_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "pre_sign_up" {
  name = "${local.pre_sign_up_name}-link"
  role = aws_iam_role.pre_sign_up.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "cognito-idp:ListUsers",
          "cognito-idp:AdminConfirmSignUp",
          "cognito-idp:AdminCreateUser",
          "cognito-idp:AdminLinkProviderForUser",
          "cognito-idp:AdminSetUserPassword",
          "cognito-idp:AdminUpdateUserAttributes",
        ]
        Resource = aws_cognito_user_pool.main.arn
      },
    ]
  })
}

resource "aws_lambda_function" "pre_sign_up" {
  function_name    = local.pre_sign_up_name
  role             = aws_iam_role.pre_sign_up.arn
  runtime          = "nodejs22.x"
  handler          = "pre-sign-up.handler"
  filename         = data.archive_file.pre_sign_up.output_path
  source_code_hash = data.archive_file.pre_sign_up.output_base64sha256

  # **Cognito gives a trigger 5 seconds, whatever the Lambda's own timeout,
  # and a late reply is a failed sign-in.** The memory is CPU: measured on a
  # dev stack, the cold create path (SDK load, ListUsers, AdminCreateUser,
  # AdminSetUserPassword, AdminLinkProviderForUser) TIMED OUT at 256 MB and
  # took 2.3 s at 1024 MB. Do not "right-size" this down to the 106 MB it
  # uses. The timeout matches Cognito's so a hang fails here, with a log
  # line, rather than there.
  timeout     = 5
  memory_size = 1024

  environment {
    variables = {
      HUMBUGG_IDENTITY_PROVIDERS = join(",", local.identity_provider_names)
    }
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "pre_sign_up" {
  name              = "/aws/lambda/${local.pre_sign_up_name}"
  retention_in_days = 14
  tags              = var.tags
}

resource "aws_lambda_permission" "pre_sign_up" {
  statement_id  = "AllowCognitoInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.pre_sign_up.function_name
  principal     = "cognito-idp.amazonaws.com"
  source_arn    = aws_cognito_user_pool.main.arn
}
