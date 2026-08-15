#!/usr/bin/env bash
#
# Create a studio user.
#
# The pool is admin-create-user only (no public self-signup), so every account
# is provisioned here. Safe to run repeatedly: an existing user is left
# untouched.
#
# Required env:
#   STUDIO_EMAIL     login email (used as the username)
# Optional:
#   STUDIO_PASSWORD  permanent password. If unset, Cognito emails a temporary
#                    one and the app's "set a password" step handles the rest.
#   USER_POOL_ID     defaults to the value Terraform wrote to SSM
#   AWS_REGION       defaults to us-east-1
#
# Usage:
#   STUDIO_EMAIL=you@example.com ./studio/scripts/create-user.sh

set -euo pipefail

: "${STUDIO_EMAIL:?STUDIO_EMAIL is required}"
REGION="${AWS_REGION:-us-east-1}"

if [ -z "${USER_POOL_ID:-}" ]; then
  USER_POOL_ID=$(aws ssm get-parameter \
    --name /studio/prod/cognito-user-pool-id \
    --query Parameter.Value --output text --region "$REGION")
fi

if aws cognito-idp admin-get-user \
  --user-pool-id "$USER_POOL_ID" \
  --username "$STUDIO_EMAIL" \
  --region "$REGION" >/dev/null 2>&1; then
  echo "User '$STUDIO_EMAIL' already exists — leaving it untouched."
  exit 0
fi

echo "Creating user '$STUDIO_EMAIL' in $USER_POOL_ID..."

# SUPPRESS the invite email only when we are setting the password ourselves;
# otherwise Cognito needs to send the temporary one.
if [ -n "${STUDIO_PASSWORD:-}" ]; then
  aws cognito-idp admin-create-user \
    --user-pool-id "$USER_POOL_ID" \
    --username "$STUDIO_EMAIL" \
    --user-attributes Name=email,Value="$STUDIO_EMAIL" Name=email_verified,Value=true \
    --message-action SUPPRESS \
    --region "$REGION" >/dev/null

  aws cognito-idp admin-set-user-password \
    --user-pool-id "$USER_POOL_ID" \
    --username "$STUDIO_EMAIL" \
    --password "$STUDIO_PASSWORD" \
    --permanent \
    --region "$REGION"

  echo "User '$STUDIO_EMAIL' created with a permanent password."
else
  aws cognito-idp admin-create-user \
    --user-pool-id "$USER_POOL_ID" \
    --username "$STUDIO_EMAIL" \
    --user-attributes Name=email,Value="$STUDIO_EMAIL" Name=email_verified,Value=true \
    --region "$REGION" >/dev/null

  echo "User '$STUDIO_EMAIL' created. Cognito emailed a temporary password;"
  echo "signing in with it prompts for a new one."
fi
