#!/usr/bin/env bash
# Print an ID token for this machine's dev-pool teacher account.
#
# This is what turns a curl against the local API into a real signed-in request:
#
#   curl -H "Authorization: Bearer $(./classroom/scripts/dev-token.sh)" \
#        http://localhost:8001/api/pages
#
# **Only stdout carries the token.** Every log line here goes to stderr so the
# command substitution above gets the token and nothing else.
#
# **An ID token, not an access token.** The deployed authorizer is a
# COGNITO_USER_POOLS authorizer, which validates an identity token; the local
# dev server checks `token_use == "id"` for the same reason. `--access` exists
# to prove that rejection, not to authenticate with.
#
# **Dev only, and it refuses to be pointed anywhere else.** The pool comes from
# this machine's Terraform state, which describes one environment. A --prod flag
# here would be a token for a real teacher's pool in a script that prints
# credentials to a terminal. To exercise prod, sign in at
# classroom.andreas.services in a browser.
#
# Usage:
#   ./classroom/scripts/dev-token.sh           # ID token
#   ./classroom/scripts/dev-token.sh --access  # access token instead
#
# The password comes from CLASSROOM_DEV_USER_PASSWORD if exported, else
# ~/.config/andreas-services/classroom/dev.env, else a no-echo prompt.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dev-aws-common.sh
source "$SCRIPT_DIR/dev-aws-common.sh"

TOKEN_KIND="id"
ALLOW_PROMPT=true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) [[ $# -ge 2 ]] || die "--profile requires a value."; AWS_PROFILE_VALUE="$2"; shift ;;
    --region) [[ $# -ge 2 ]] || die "--region requires a value."; AWS_REGION_VALUE="$2"; shift ;;
    --access) TOKEN_KIND="access" ;;
    # For a test harness or anything else non-interactive: fail with a named
    # variable instead of blocking forever on a prompt nobody is there to answer.
    --no-prompt) ALLOW_PROMPT=false ;;
    --help|-h)
      printf 'Usage: %s [--profile NAME] [--region REGION] [--access] [--no-prompt]\n' "$0"
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done

for command in aws jq uv; do require_command "$command"; done
load_machine_id false
load_aws_identity
load_dev_stack_outputs
load_dev_user_email
load_dev_user_password "$ALLOW_PROMPT"

log "Signing in as $CLASSROOM_DEV_USER_EMAIL against $DEV_POOL_ID."

# `uv run` on a PEP 723 script: the dependency is declared in dev-token.py's own
# header, so there is no environment to create first and nothing to add to
# backend/, which should not carry a test-only Cognito client into its lockfile.
#
# Everything the script needs arrives in the environment. Nothing is passed as
# an argument, because argv is world-readable in `ps`.
CLASSROOM_DEV_POOL_ID="$DEV_POOL_ID" \
CLASSROOM_DEV_CLIENT_ID="$DEV_CLIENT_ID" \
CLASSROOM_DEV_USER_EMAIL="$CLASSROOM_DEV_USER_EMAIL" \
CLASSROOM_DEV_USER_PASSWORD="$CLASSROOM_DEV_USER_PASSWORD" \
CLASSROOM_DEV_TOKEN_KIND="$TOKEN_KIND" \
AWS_REGION="$AWS_REGION_VALUE" \
  uv run --quiet "$SCRIPT_DIR/dev-token.py"
