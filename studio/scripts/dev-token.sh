#!/usr/bin/env bash
# Print an ID token for this machine's dev-pool test account.
#
# The missing half of the dev environment: #289 wants integration tests that
# validate "a real dev-pool ID token" through `identity.caller_sub`, and until
# this existed there was no way to obtain one. It is also what turns a curl
# against the local API into a real signed-in request:
#
#   curl -H "Authorization: Bearer $(./studio/scripts/dev-token.sh)" \
#        http://localhost:8000/api/libraries
#
# **Only stdout carries the token.** Every log line here goes to stderr so the
# command substitution above gets the token and nothing else.
#
# **Dev only, and it refuses to be pointed anywhere else.** The pool comes from
# this machine's Terraform state, which describes one environment. Studio ran
# local-against-prod until August 2026 and the dev stack exists to end that; a
# --prod flag here would be the habit growing back with a token in its hand. To
# exercise prod, sign in to studio.andreas.services in a browser — that is the
# deliberate answer, not a missing feature.
#
# Usage:
#   ./studio/scripts/dev-token.sh              # ID token
#   ./studio/scripts/dev-token.sh --access     # access token instead
#
# The password comes from STUDIO_DEV_USER_PASSWORD if exported, else
# ~/.config/andreas-services/studio/dev.env, else a no-echo prompt.
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
load_dev_user_password "$ALLOW_PROMPT"

log "Signing in as $STUDIO_DEV_USER_EMAIL against $DEV_POOL_ID."

# `uv run` on a PEP 723 script: the dependency is declared in dev-token.py's own
# header, so there is no environment to create first and nothing to add to
# backend/ or pipeline/ — neither of which should carry a test-only Cognito
# client into its lockfile.
#
# Everything the script needs arrives in the environment. Nothing is passed as
# an argument, because argv is world-readable in `ps`.
STUDIO_DEV_POOL_ID="$DEV_POOL_ID" \
STUDIO_DEV_CLIENT_ID="$DEV_CLIENT_ID" \
STUDIO_DEV_USER_EMAIL="$STUDIO_DEV_USER_EMAIL" \
STUDIO_DEV_USER_PASSWORD="$STUDIO_DEV_USER_PASSWORD" \
STUDIO_DEV_TOKEN_KIND="$TOKEN_KIND" \
AWS_REGION="$AWS_REGION_VALUE" \
  uv run --quiet "$SCRIPT_DIR/dev-token.py"
