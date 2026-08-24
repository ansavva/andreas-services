#!/usr/bin/env bash
#
# Idempotently provision a studio account, and optionally grant it a library.
#
# The pool is admin-create-user only (no public self-signup), so every account
# is created here. Defaults point at **prod**, like `add-member.sh` and unlike
# everything named `dev-*`.
#
# Required env:
#   STUDIO_EMAIL     login email (used as the username)
# Optional:
#   STUDIO_PASSWORD  permanent password to converge to. Unset, Cognito emails a
#                    temporary one and the account is left at that.
#   STUDIO_LIBRARY   `lib-<uuid>` to grant membership on, via add-member.sh
#   STUDIO_ROLE      owner | member  (default: member) — passed to add-member.sh
#   USER_POOL_ID     defaults to the value Terraform wrote to SSM
#   AWS_REGION       defaults to us-east-1
# Flags:
#   --check          report what would happen and change nothing
#   --no-converge    create if missing, but never touch an existing password
#
# **The email and password can come from
# `~/.config/andreas-services/studio/prod.env` instead**, which is where this
# service already keeps a password that must not be near source control — the
# dev half has read `dev.env` since it existed, and this is the prod half of the
# same arrangement. The environment still wins, so a one-off run can override
# either without editing the file:
#
#   STUDIO_PROD_USER_EMAIL=you@example.com
#   STUDIO_PROD_USER_PASSWORD=…
#
# `STUDIO_EMAIL` and `STUDIO_PASSWORD` are accepted as keys in that file too, so
# it can be written either way round. The `STUDIO_PROD_USER_*` spelling is the
# one to prefer: it mirrors `STUDIO_DEV_USER_PASSWORD` in `dev.env`, and it says
# which pool the value belongs to — which matters in a file that sits next to
# `dev.env` and is one typo away from resetting the wrong account's password.
#
# Usage:
#   ./studio/scripts/create-user.sh                       # both from prod.env
#   STUDIO_EMAIL=you@example.com ./studio/scripts/create-user.sh
#   STUDIO_EMAIL=… STUDIO_PASSWORD=… STUDIO_LIBRARY=lib-… ./studio/scripts/create-user.sh
#
# **An account without a membership can sign in and see nothing.** Membership is
# the whole of authorisation in this service, so a new account reaches no library
# until `add-member.sh` writes it a row. That used to be a separate step nothing
# pointed at, which is exactly how an account ends up looking broken when it is
# merely empty. Set `STUDIO_LIBRARY` and this script grants it; leave it unset
# and the script says, loudly, what is still missing and how to fix it.
#
# **A re-run converges the password when `STUDIO_PASSWORD` is set.** The old
# behaviour exited early on an existing account, so this was the one way to
# reset a studio password that silently did nothing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

# The prod half of the config-directory arrangement `dev-aws-common.sh` already
# implements for dev. Spelled out here rather than sourced from that file: this
# script defaults to PROD and takes no machine id, and pulling in the dev
# helpers to reach one path would drag a dev stack's assumptions into a prod
# run. Sourcing the file is how the dev half reads its own, so the mechanism
# matches even though the code does not.
PROD_ENV_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/andreas-services/studio/prod.env"
if [ -f "$PROD_ENV_FILE" ] &&
  { [ -z "${STUDIO_EMAIL:-}" ] || [ -z "${STUDIO_PASSWORD:-}" ]; }; then
  # **Held before sourcing, restored after.** The file may spell the keys
  # `STUDIO_EMAIL` / `STUDIO_PASSWORD`, and sourcing it would then overwrite
  # what the caller passed — silently addressing a different account than the
  # command line named, which is the one failure this must not have.
  _caller_email="${STUDIO_EMAIL:-}"
  _caller_password="${STUDIO_PASSWORD:-}"
  # shellcheck source=/dev/null
  . "$PROD_ENV_FILE"
  STUDIO_EMAIL="${_caller_email:-${STUDIO_EMAIL:-${STUDIO_PROD_USER_EMAIL:-}}}"
  STUDIO_PASSWORD="${_caller_password:-${STUDIO_PASSWORD:-${STUDIO_PROD_USER_PASSWORD:-}}}"
  unset _caller_email _caller_password
fi

: "${STUDIO_EMAIL:?STUDIO_EMAIL is required (or STUDIO_PROD_USER_EMAIL in $PROD_ENV_FILE)}"
REGION="${AWS_REGION:-us-east-1}"

if [ -z "${USER_POOL_ID:-}" ]; then
  USER_POOL_ID=$(aws ssm get-parameter \
    --name /studio/prod/cognito-user-pool-id \
    --query Parameter.Value --output text --region "$REGION")
fi

user_exists() {
  aws cognito-idp admin-get-user \
    --user-pool-id "$USER_POOL_ID" \
    --username "$STUDIO_EMAIL" \
    --region "$REGION" >/dev/null 2>&1
}

if user_exists; then
  EXISTS=true
else
  EXISTS=false
fi

if [ "$CHECK" = true ]; then
  if [ "$EXISTS" = true ]; then
    echo "'$STUDIO_EMAIL' exists in $USER_POOL_ID."
    if [ -n "${STUDIO_PASSWORD:-}" ] && [ "$CONVERGE" = true ]; then
      echo "A real run would converge its password to STUDIO_PASSWORD."
    fi
  else
    echo "'$STUDIO_EMAIL' does NOT exist in $USER_POOL_ID; a real run would create it."
  fi
  if [ -n "${STUDIO_LIBRARY:-}" ]; then
    echo "A real run would grant membership on $STUDIO_LIBRARY."
  fi
  exit 0
fi

if [ "$EXISTS" = false ]; then
  echo "Creating '$STUDIO_EMAIL' in $USER_POOL_ID..."
  if [ -n "${STUDIO_PASSWORD:-}" ]; then
    # SUPPRESS the invite only when we set the password ourselves; otherwise
    # Cognito has a temporary one that needs delivering.
    aws cognito-idp admin-create-user \
      --user-pool-id "$USER_POOL_ID" \
      --username "$STUDIO_EMAIL" \
      --user-attributes Name=email,Value="$STUDIO_EMAIL" Name=email_verified,Value=true \
      --message-action SUPPRESS \
      --region "$REGION" >/dev/null
  else
    aws cognito-idp admin-create-user \
      --user-pool-id "$USER_POOL_ID" \
      --username "$STUDIO_EMAIL" \
      --user-attributes Name=email,Value="$STUDIO_EMAIL" Name=email_verified,Value=true \
      --region "$REGION" >/dev/null
    echo "Created. Cognito emailed a temporary password; signing in with it prompts"
    echo "for a new one. Set STUDIO_PASSWORD to skip that."
  fi
fi

if [ -n "${STUDIO_PASSWORD:-}" ]; then
  if [ "$EXISTS" = true ] && [ "$CONVERGE" = false ]; then
    echo "'$STUDIO_EMAIL' exists and --no-converge was passed; password untouched."
  else
    if ! aws cognito-idp admin-set-user-password \
      --user-pool-id "$USER_POOL_ID" \
      --username "$STUDIO_EMAIL" \
      --password "$STUDIO_PASSWORD" \
      --permanent \
      --region "$REGION"; then
      echo "admin-set-user-password failed. If it rejected the password, the AWS" >&2
      echo "error above names the rule it broke — read that rather than guessing," >&2
      echo "because the policy differs per pool (symbols are required on some)." >&2
      exit 1
    fi
    echo "Password set from STUDIO_PASSWORD."
  fi
fi

# The membership half. Delegated to add-member.sh rather than reimplemented:
# that script is the only thing that writes a membership row, and two writers
# would be two chances to write it differently.
if [ -n "${STUDIO_LIBRARY:-}" ]; then
  echo "Granting membership on $STUDIO_LIBRARY..."
  STUDIO_EMAIL="$STUDIO_EMAIL" \
  STUDIO_LIBRARY="$STUDIO_LIBRARY" \
  STUDIO_ROLE="${STUDIO_ROLE:-member}" \
  USER_POOL_ID="$USER_POOL_ID" \
  AWS_REGION="$REGION" \
    bash "$SCRIPT_DIR/add-member.sh"
else
  echo
  echo "WARNING: '$STUDIO_EMAIL' is not a member of any library, so it can sign in"
  echo "and will see nothing. Grant one with:"
  echo
  echo "  STUDIO_EMAIL=$STUDIO_EMAIL STUDIO_LIBRARY=lib-… $SCRIPT_DIR/add-member.sh"
  echo
fi
