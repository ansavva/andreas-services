#!/usr/bin/env bash
#
# Idempotently bootstrap the Cognito admin user for the website admin dashboard.
#
# The user pool is admin-create-user only (no public self-signup), so the admin
# must be provisioned out of band. CI runs this after the pool is applied; it can
# also be run locally against any environment.
#
# Required env:
#   USER_POOL_ID    Cognito user pool ID
#   ADMIN_EMAIL     admin login email (used as the username)
#   ADMIN_PASSWORD  permanent password to set
# Optional:
#   AWS_REGION      defaults to us-east-1
#
# Safe to run repeatedly: an existing user is left untouched. The created user
# gets a *permanent* password so USER_PASSWORD_AUTH login works immediately.

set -euo pipefail

: "${USER_POOL_ID:?USER_POOL_ID is required}"
: "${ADMIN_EMAIL:?ADMIN_EMAIL is required}"
: "${ADMIN_PASSWORD:?ADMIN_PASSWORD is required}"
REGION="${AWS_REGION:-us-east-1}"

if aws cognito-idp admin-get-user \
  --user-pool-id "$USER_POOL_ID" \
  --username "$ADMIN_EMAIL" \
  --region "$REGION" >/dev/null 2>&1; then
  echo "Admin user '$ADMIN_EMAIL' already exists — leaving it untouched."
  exit 0
fi

echo "Creating admin user '$ADMIN_EMAIL'..."
aws cognito-idp admin-create-user \
  --user-pool-id "$USER_POOL_ID" \
  --username "$ADMIN_EMAIL" \
  --user-attributes Name=email,Value="$ADMIN_EMAIL" Name=email_verified,Value=true \
  --message-action SUPPRESS \
  --region "$REGION" >/dev/null

aws cognito-idp admin-set-user-password \
  --user-pool-id "$USER_POOL_ID" \
  --username "$ADMIN_EMAIL" \
  --password "$ADMIN_PASSWORD" \
  --permanent \
  --region "$REGION"

echo "Admin user '$ADMIN_EMAIL' created and confirmed."
