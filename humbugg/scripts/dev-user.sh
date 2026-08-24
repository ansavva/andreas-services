#!/usr/bin/env bash
#
# Create (or converge) the humbugg dev-stack test account.
#
# Closes the gap that made humbugg the only service with a dev pool and no way
# to put a user in it: the pool allows self-signup, so the documented route was
# "register through the local app by hand", which every developer did slightly
# differently and no test could rely on. This gives every machine the *same*
# account with the same password, so a scripted sign-in works anywhere.
#
# The account is whichever address `HUMBUGG_DEV_USER_EMAIL` names, from the
# environment or from `dev.env` — no address is committed. Self-signup still
# works and is untouched — this is a fixture, not a gate.
#
# The password comes from HUMBUGG_DEV_USER_PASSWORD if exported, else from
# ~/.config/andreas-services/humbugg/dev.env, else --generate-password, else a
# no-echo prompt.
#
# Usage:
#   ./humbugg/scripts/dev-user.sh
#   ./humbugg/scripts/dev-user.sh --generate-password   # non-interactive
#   ./humbugg/scripts/dev-user.sh --check               # report, change nothing
#
# **A re-run converges the password.** Rotating the value in `dev.env` and
# re-running is how you reset this account; it is deliberately not a way to
# overwrite a *person's* password, because the account is a fixture nobody owns.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/dev-aws-common.sh"

CHECK=false
GENERATE=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) AWS_PROFILE_VALUE="$2"; shift ;;
    --region)  AWS_REGION_VALUE="$2";  shift ;;
    --check)   CHECK=true ;;
    --generate-password) GENERATE=true ;;
    -h|--help)
      printf 'Usage: %s [--profile NAME] [--region REGION] [--check] [--generate-password]\n' "$0"
      exit 0
      ;;
    *) die "Unknown argument: $1" ;;
  esac
  shift
done

require_command aws
require_command jq
require_command terraform

load_machine_id false
load_aws_identity
load_dev_user_email
terraform_init

DEV_POOL_ID="$(jq -r '.cognito_user_pool_id.value' <<<"$(terraform_output_json)")"
[[ -n "$DEV_POOL_ID" && "$DEV_POOL_ID" != "null" ]] ||
  die "No dev pool in Terraform outputs. Run ./humbugg/scripts/dev-aws-setup.sh first."

log "Pool:    $DEV_POOL_ID"
log "Account: $HUMBUGG_DEV_USER_EMAIL"

user_exists() {
  aws_dev cognito-idp admin-get-user \
    --user-pool-id "$DEV_POOL_ID" --username "$HUMBUGG_DEV_USER_EMAIL" >/dev/null 2>&1
}

if [[ "$CHECK" == "true" ]]; then
  # Deliberately does NOT check the password. Verifying it means signing in,
  # and a --check that authenticates is a --check that can lock an account out
  # of a pool with attempt limits.
  user_exists ||
    die "No '$HUMBUGG_DEV_USER_EMAIL' in $DEV_POOL_ID. Run ./humbugg/scripts/dev-user.sh."
  ok "Account exists. Its password was not verified."
  exit 0
fi

load_dev_user_password true "$GENERATE"

if user_exists; then
  log "Account exists; converging its password."
else
  # SUPPRESS because the password is set below, and because `.test` is
  # unroutable — an invite would bounce into Cognito's own bounce accounting
  # rather than reach anyone.
  aws_dev cognito-idp admin-create-user \
    --user-pool-id "$DEV_POOL_ID" \
    --username "$HUMBUGG_DEV_USER_EMAIL" \
    --user-attributes Name=email,Value="$HUMBUGG_DEV_USER_EMAIL" Name=email_verified,Value=true \
    --message-action SUPPRESS >/dev/null
  log "Account created."
fi

# --permanent, so there is no FORCE_CHANGE_PASSWORD challenge for a headless
# SRP sign-in to get stuck behind.
aws_dev cognito-idp admin-set-user-password \
  --user-pool-id "$DEV_POOL_ID" \
  --username "$HUMBUGG_DEV_USER_EMAIL" \
  --password "$HUMBUGG_DEV_USER_PASSWORD" \
  --permanent ||
  die "admin-set-user-password failed. If it rejected the password, the AWS error above names the rule it broke — the policy differs per pool."

ok "Account '$HUMBUGG_DEV_USER_EMAIL' ready in $DEV_POOL_ID."
