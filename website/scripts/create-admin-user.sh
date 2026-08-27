#!/usr/bin/env bash
#
# Idempotently provision the Cognito admin user for the website admin dashboard.
#
# The pool is admin-create-user only (no public self-signup), so the admin must
# be provisioned out of band. CI runs this after the pool is applied; it also
# runs locally against any environment.
#
# Required env:
#   USER_POOL_ID           Cognito user pool ID
#   WEBSITE_ADMIN_EMAIL   admin login email (used as the username)
#   WEBSITE_ADMIN_PASSWORDpermanent password to converge to
#
# The bare `ADMIN_EMAIL` / `ADMIN_PASSWORD` are still accepted, second, because
# that is what this took until now. Prefer the prefixed pair: the bare names are
# the same two in scout's script, so one `export ADMIN_PASSWORD` in a
# shell serves both and sets a password on whichever pool is run next. The
# GitHub secrets have always been namespaced; this closes the gap between them.
# Optional:
#   AWS_REGION      defaults to us-east-1
# Flags:
#   --check         report what would happen and change nothing
#   --no-converge   create if missing, but never touch an existing password
#
# **A re-run converges the password, and that is the point.** This script used
# to exit early on an existing user, which meant rotating WEBSITE_ADMIN_PASSWORD and
# redeploying printed "leaving it untouched" and changed nothing: the secret and
# the real password drifted apart with no error and no way to notice. The secret
# is the source of truth now, so a rotation takes effect on the next deploy.
#
# The consequence to know: a password changed by hand in the console is reverted
# on the next run. Change it in WEBSITE_ADMIN_PASSWORD instead, or pass --no-converge.
#
# The password is set `--permanent`, so sign-in does not open on a
# FORCE_CHANGE_PASSWORD screen. The hosted pages can serve that challenge, but
# a password the script would revert on the next run is not worth setting.

set -euo pipefail

CHECK=false
CONVERGE=true
while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK=true ;;
    --no-converge) CONVERGE=false ;;
    -h|--help)
      printf 'Usage: %s [--check] [--no-converge]\n' "$0"
      exit 0
      ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

: "${USER_POOL_ID:?USER_POOL_ID is required}"

# Prefixed first, bare second. Assigned to the bare names because everything
# below reads those, and because it keeps the two services' scripts identical
# apart from the prefix.
ADMIN_EMAIL="${WEBSITE_ADMIN_EMAIL:-${ADMIN_EMAIL:-}}"
ADMIN_PASSWORD="${WEBSITE_ADMIN_PASSWORD:-${ADMIN_PASSWORD:-}}"
# Which name the value actually came from, so the messages below can say so
# instead of naming the preferred one and being wrong half the time. Whoever is
# reading the output is about to go and edit whichever variable it names.
PASSWORD_VAR="WEBSITE_ADMIN_PASSWORD"
if [ -z "${WEBSITE_ADMIN_PASSWORD:-}" ] && [ -n "${ADMIN_PASSWORD:-}" ]; then
  PASSWORD_VAR="ADMIN_PASSWORD"
fi
: "${ADMIN_EMAIL:?WEBSITE_ADMIN_EMAIL is required}"
# Not required for --check: reporting whether an account exists needs no
# password, and demanding one would mean inventing a throwaway value to ask a
# read-only question.
[ "$CHECK" = true ] || : "${ADMIN_PASSWORD:?WEBSITE_ADMIN_PASSWORD is required}"
REGION="${AWS_REGION:-us-east-1}"

user_exists() {
  aws cognito-idp admin-get-user \
    --user-pool-id "$USER_POOL_ID" \
    --username "$ADMIN_EMAIL" \
    --region "$REGION" >/dev/null 2>&1
}

if user_exists; then
  EXISTS=true
else
  EXISTS=false
fi

if [ "$CHECK" = true ]; then
  if [ "$EXISTS" = true ]; then
    echo "Admin '$ADMIN_EMAIL' exists in $USER_POOL_ID."
    if [ "$CONVERGE" = true ]; then
      echo "A real run would converge its password to $PASSWORD_VAR."
    fi
  else
    echo "Admin '$ADMIN_EMAIL' does NOT exist in $USER_POOL_ID; a real run would create it."
  fi
  exit 0
fi

if [ "$EXISTS" = false ]; then
  echo "Creating admin '$ADMIN_EMAIL' in $USER_POOL_ID..."
  # SUPPRESS because the password is set below: there is no temporary one worth
  # emailing, and the invite would be the only mail this pool ever sent.
  aws cognito-idp admin-create-user \
    --user-pool-id "$USER_POOL_ID" \
    --username "$ADMIN_EMAIL" \
    --user-attributes Name=email,Value="$ADMIN_EMAIL" Name=email_verified,Value=true \
    --message-action SUPPRESS \
    --region "$REGION" >/dev/null
elif [ "$CONVERGE" = false ]; then
  echo "Admin '$ADMIN_EMAIL' exists and --no-converge was passed."
  echo "Its password is NOT being checked or changed, so it may differ from $PASSWORD_VAR."
  exit 0
else
  echo "Admin '$ADMIN_EMAIL' exists; converging its password."
fi

if ! aws cognito-idp admin-set-user-password \
  --user-pool-id "$USER_POOL_ID" \
  --username "$ADMIN_EMAIL" \
  --password "$ADMIN_PASSWORD" \
  --permanent \
  --region "$REGION"; then
  echo "admin-set-user-password failed. If it rejected the password, the AWS" >&2
  echo "error above names the rule it broke — read that rather than guessing," >&2
  echo "because the policy differs per pool (symbols are required on some)." >&2
  exit 1
fi

echo "Admin '$ADMIN_EMAIL' is present with the password from $PASSWORD_VAR."
