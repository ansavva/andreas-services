#!/usr/bin/env bash
# Converge this machine's dev-pool test account.
#
# The dev Cognito pool is `allow_admin_create_user_only`, like prod's, so the
# one account in it is created here. `dev-token.sh` signs in as exactly this
# account, and both read `STUDIO_DEV_USER_EMAIL` from `dev-aws-common.sh` so
# they cannot drift onto two different people.
#
# **This converges where `create-user.sh` leaves well alone**, and the
# difference is deliberate rather than a fork. `create-user.sh` provisions a
# *human* into the prod pool and exits early if the account exists, because
# overwriting a person's password is the last thing it should do on a re-run.
# This account is a fixture: rotating the password in `dev.env` and re-running
# must converge it, exactly as re-running a seed converges a row.
#
# Nothing here writes to prod. The pool comes from this machine's Terraform
# state, and a machine with no dev stack is told to run `dev-aws-setup.sh`
# rather than being pointed at anything else.
#
# Usage:
#   ./studio/scripts/dev-user.sh                 # create or converge
#   ./studio/scripts/dev-user.sh --check         # read-only: does it exist?
#
# The password comes from STUDIO_DEV_USER_PASSWORD if exported, else
# ~/.config/andreas-services/studio/dev.env, else a no-echo prompt. There is no
# default and there will not be one.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dev-aws-common.sh
source "$SCRIPT_DIR/dev-aws-common.sh"

CHECK_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) [[ $# -ge 2 ]] || die "--profile requires a value."; AWS_PROFILE_VALUE="$2"; shift ;;
    --region) [[ $# -ge 2 ]] || die "--region requires a value."; AWS_REGION_VALUE="$2"; shift ;;
    --check) CHECK_ONLY=1 ;;
    --help|-h)
      printf 'Usage: %s [--profile NAME] [--region REGION] [--check]\n' "$0"
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done

for command in aws jq; do require_command "$command"; done
# --check must not mint a machine ID as a side effect, for the reason
# dev-aws-setup.sh gives: asking whether a machine is set up should not be what
# sets it up.
load_machine_id false
load_aws_identity
load_dev_stack_outputs

log "Cognito user pool: $DEV_POOL_ID"
log "Account: $STUDIO_DEV_USER_EMAIL"

user_exists() {
  aws_dev cognito-idp admin-get-user \
    --user-pool-id "$DEV_POOL_ID" --username "$STUDIO_DEV_USER_EMAIL" >/dev/null 2>&1
}

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  # Deliberately does NOT check the password. Verifying it means signing in,
  # which mints a token and needs the secret — that is `dev-token.sh`'s job, and
  # a read-only check should not require a credential to answer "does this
  # account exist".
  user_exists || die "No '$STUDIO_DEV_USER_EMAIL' in $DEV_POOL_ID. Run ./studio/scripts/dev-user.sh."
  ok "The dev test account exists."
  exit 0
fi

load_dev_user_password

if user_exists; then
  log "Account exists; converging its password."
else
  # MessageAction=SUPPRESS because the password is set below and there is
  # nothing to email — and because `.test` is unroutable, so an invite would
  # bounce into Cognito's own bounce accounting rather than reach anyone.
  aws_dev cognito-idp admin-create-user \
    --user-pool-id "$DEV_POOL_ID" \
    --username "$STUDIO_DEV_USER_EMAIL" \
    --user-attributes Name=email,Value="$STUDIO_DEV_USER_EMAIL" Name=email_verified,Value=true \
    --message-action SUPPRESS >/dev/null
  log "Account created."
fi

# --permanent, so there is no FORCE_CHANGE_PASSWORD challenge for a headless
# SRP sign-in to get stuck behind. The value arrives through the environment
# rather than on the command line: an argument is visible in `ps` to every
# other process on the machine for as long as the call takes.
aws_dev cognito-idp admin-set-user-password \
  --user-pool-id "$DEV_POOL_ID" \
  --username "$STUDIO_DEV_USER_EMAIL" \
  --password "$STUDIO_DEV_USER_PASSWORD" \
  --permanent ||
  die "admin-set-user-password failed. If it rejected the password it did not meet the pool policy: 12+ characters, upper, lower and a digit."

ok "The dev test account is ready."
printf '\nMint an ID token for it with:\n  ./studio/scripts/dev-token.sh\n'
