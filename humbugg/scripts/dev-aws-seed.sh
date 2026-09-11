#!/usr/bin/env bash
#
# Make this machine's dev stack signable-in AND seeded: ensure every person in
# seeds/dev.json exists in THIS MACHINE's Cognito pool, then load that fixture
# into this machine's dev stack through the running local API.
#
#   ./humbugg/scripts/dev-aws-seed.sh
#   ./humbugg/scripts/dev-aws-seed.sh --check     # report what is missing, write nothing
#
# ## Why this exists
#
# The interesting states of a gift exchange need more than one person. Free
# seats six participants, organizer included, and the 402 a seventh gets is
# raised for a different signed-in account than the organizer's; Plus is bought
# per exchange through Stripe. Neither is reachable from one account and one
# browser, and "sign up six more people by hand in private windows" is the kind
# of setup that gets done once, differently on every machine, and then never
# again. So the fixture says who exists and what they are in, and this puts it
# there — the same way, every time, on every machine.
#
# ## The password, and ~/.config/andreas-services/humbugg/dev.env
#
# Every account this creates shares ONE password: HUMBUGG_DEV_USER_PASSWORD,
# resolved the way dev-user.sh resolves it — the environment, then dev.env,
# then a no-echo prompt. They are all this machine's throwaway seats in a pool
# whose entire contents are this fixture, and one value that rotates cleanly
# beats seven that rotate by hand. The fixture carries the ADDRESSES (all
# `.test`, RFC 2606 — never a real mailbox) and never a password: this repo is
# public, and a password a human typed must never end up in a committed file.
# dev.env sits outside the repo for the same reason.
#
# A re-run converges every password to the current value, which is how you
# rotate it: change dev.env, run this again.
#
# ## What is actually in the seed
#
# seeds/dev.json, which is the answer to "what is on a developer's machine" and
# is reviewable as a diff. This script does not describe the data; it only
# says WHERE to put it, and the account half lives here rather than in the
# loader because it is the half that needs AWS credentials — the loader talks
# only to the local API, as the app does. seeds/README.md has the shape.
#
# ## Why this is shell and the loading is Node
#
# The split follows one question: does the step need to know the shape of our
# data? Not here. This file resolves an ENVIRONMENT — the machine id, the pool
# in this machine's Terraform state, AWS credentials — and creates accounts
# with the same `ensure_pool_user` dev-user.sh uses. Building rows does need
# the shape, and the shape belongs to the API: the loader (dev-seed.mjs) signs
# in as each person over real SRP and makes the requests the app makes, so a
# seeded row is a row the service wrote. amazon-cognito-identity-js is already
# a dependency of this directory (smoke-session.mjs), which is why it is Node.
#
# ## Scope
#
# DEV ONLY, and not parameterised on purpose. A script that creates accounts
# and could be pointed at the prod pool by changing one argument is a script
# that eventually is. The pool comes from THIS machine's Terraform state and
# must be named for this machine, exactly as dev-aws-reset.sh checks before it
# deletes anything; the loader refuses any API base that is not loopback.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/dev-aws-common.sh"

CHECK=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) AWS_PROFILE_VALUE="$2"; shift ;;
    --region)  AWS_REGION_VALUE="$2";  shift ;;
    --check)   CHECK=true ;;
    -h|--help)
      printf 'Usage: %s [--profile NAME] [--region REGION] [--check]\n\n' "$0"
      printf 'Ensures every person in seeds/dev.json exists in this machine'"'"'s pool, then\n'
      printf 'loads that fixture through the local API (start it: dev-up.sh).\n'
      printf 'Edit the fixture to change WHAT is seeded; this script only says where.\n'
      exit 0
      ;;
    *) die "Unknown argument: $1" ;;
  esac
  shift
done

for command in aws jq terraform node npm; do require_command "$command"; done

FIXTURE="$HUMBUGG_DIR/seeds/dev.json"
[[ -f "$FIXTURE" ]] || die "No fixture at $FIXTURE."

load_machine_id false
load_aws_identity
require_dev_env
terraform_init
outputs="$(terraform_output_json)"

# Belt and braces on "dev only", exactly as dev-aws-reset.sh does before it
# deletes anything: the pool must be named for THIS machine.
DEV_POOL_ID="$(jq -r '.cognito_user_pool_id.value // empty' <<<"$outputs")"
[[ -n "$DEV_POOL_ID" ]] ||
  die "No dev pool in Terraform outputs. Run ./humbugg/scripts/dev-aws-setup.sh first."
expected_pool_name="$RESOURCE_PREFIX-development"
pool_name="$(aws_dev cognito-idp describe-user-pool --user-pool-id "$DEV_POOL_ID" \
  --query 'UserPool.Name' --output text)"
[[ "$pool_name" == "$expected_pool_name" ]] ||
  die "Refusing: Cognito pool '$DEV_POOL_ID' is named '$pool_name', not '$expected_pool_name'."

# ── The accounts ────────────────────────────────────────────────────────────────
# FROM THE FIXTURE, not from HUMBUGG_DEV_USER_EMAIL: that names the one account
# the e2e helper signs in as, and it should be one of these, but the fixture is
# what says who exists. Not mapfile — macOS ships bash 3.2.
ACCOUNT_EMAILS=()
while IFS= read -r email; do
  ACCOUNT_EMAILS+=("$email")
done < <(jq -r '[.people[].email] | unique | .[]' "$FIXTURE")
[[ ${#ACCOUNT_EMAILS[@]} -gt 0 ]] || die "No people in $(basename "$FIXTURE")."
for email in "${ACCOUNT_EMAILS[@]}"; do
  [[ "$email" == *@*.test ]] ||
    die "Refusing: fixture address '$email' is not a .test address. Only RFC 2606 reserved addresses belong in a fixture."
done

log "Pool:    $DEV_POOL_ID ($pool_name)"
log "Fixture: $FIXTURE — ${#ACCOUNT_EMAILS[@]} people"

if [[ "$CHECK" == "true" ]]; then
  for email in "${ACCOUNT_EMAILS[@]}"; do
    pool_user_exists "$DEV_POOL_ID" "$email" ||
      die "No '$email' in $DEV_POOL_ID. Re-run without --check to create it."
  done
  ok "Every account exists. Passwords were not verified here; the loader signs in."
else
  load_dev_user_password true false
  for email in "${ACCOUNT_EMAILS[@]}"; do
    ensure_pool_user "$DEV_POOL_ID" "$email" "$HUMBUGG_DEV_USER_PASSWORD"
  done
  ok "${#ACCOUNT_EMAILS[@]} accounts ready in $pool_name."
fi

# ── The data ────────────────────────────────────────────────────────────────────
# The loader needs the API up — it is the app's own requests, replayed. Checked
# here so the failure names the fix rather than a refused connection.
API_BASE="$(read_env "$DEV_ENV_FILE" EXPO_PUBLIC_API_BASE_URL)"
API_BASE="${API_BASE:-http://127.0.0.1:5001/api}"
curl -fsS -m 3 "${API_BASE%/api}/health" >/dev/null 2>&1 ||
  die "No API at $API_BASE. Start it: ./humbugg/scripts/dev-up.sh (backend + Stripe listener; the Plus exchange needs both)."

# 22 packages, under a second — the same install the post-deploy smoke job does.
[[ -d "$SCRIPT_DIR/node_modules/amazon-cognito-identity-js" ]] ||
  npm ci --prefix "$SCRIPT_DIR" --silent

seed_args=(--fixture "$FIXTURE")
[[ "$CHECK" == "true" ]] && seed_args+=(--check)
node "$SCRIPT_DIR/dev-seed.mjs" "${seed_args[@]}"

if [[ "$CHECK" == "true" ]]; then
  ok "This machine matches seeds/dev.json."
else
  ok "Done. Sign in at http://localhost:8081 as any address in seeds/dev.json with the dev.env password."
fi
