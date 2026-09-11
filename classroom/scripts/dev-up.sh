#!/usr/bin/env bash
#
# Start the classroom backend and frontend together for local development.
#
#   ./classroom/scripts/dev-up.sh
#
# Backend on :8001, frontend on :5174. Ctrl+C stops both.
#
# There is no local emulator here and no DynamoDB Local: this points at the real
# per-machine dev stack, because the two things worth exercising — the Cognito
# `sub` every page is keyed by, and the sparse GSI that makes a withdrawn page
# fall out of the public lookup — are the two things a fake would get wrong
# silently.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# Credentials must resolve before the API starts; an unauthenticated backend
# fails per-request rather than at boot, which is a slower way to learn the same
# thing. Since August 2026 they are a long-lived access key in
# `~/.aws/credentials` or `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` in the
# environment, and boto3 reads both natively.
if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "AWS credentials are not valid. Put an access key in ~/.aws/credentials," >&2
  echo "or set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY. See the root CLAUDE.md." >&2
  exit 1
fi
eval "$(aws configure export-credentials --format env)"
export AWS_DEFAULT_REGION="${AWS_REGION:-us-east-1}"

# ---------------------------------------------------------------------------
# THIS MACHINE'S DEV STACK, NOT PROD.
#
# The table name and the Cognito pool both come from the dev stack's Terraform
# outputs — the same reader `dev-user.sh` and `dev-token.sh` use. Not SSM: SSM
# holds what the deploy workflow wrote, and nothing deploys a dev stack.
#
# None of the three has a default anywhere, and that is deliberate. A pool id
# that is merely *wrong* rejects every caller; one naming a different pool would
# admit that pool's teachers. `CLASSROOM_PAGES_TABLE` is resolved at import time
# by `repositories.store`, which raises when it is absent — the behaviour
# production wants.
# ---------------------------------------------------------------------------
# A subshell, because `dev-aws-common.sh`'s `die` exits and the failure here
# needs a message this script writes rather than that one.
if ! dev_stack="$(
  # shellcheck source=dev-aws-common.sh
  source "$ROOT/classroom/scripts/dev-aws-common.sh"
  load_machine_id false
  load_aws_identity
  load_dev_stack_outputs
  printf '%s\t%s\t%s\t%s\t%s\n' "$DEV_POOL_ID" "$DEV_CLIENT_ID" "$DEV_TABLE" \
    "$DEV_SPA_ORIGIN" "$DEV_LESSONS_BUCKET"
)"; then
  echo "Could not read this machine's dev stack." >&2
  echo "  The local API verifies every request's token against the dev pool, so" >&2
  echo "  it would 401 on every call. Provision one with:" >&2
  echo "    ./classroom/scripts/dev-aws-setup.sh && ./classroom/scripts/dev-user.sh" >&2
  exit 1
fi
IFS=$'\t' read -r POOL_ID CLIENT_ID PAGES_TABLE SPA_ORIGIN LESSONS_BUCKET <<<"$dev_stack"

export CLASSROOM_COGNITO_USER_POOL_ID="$POOL_ID"
export CLASSROOM_COGNITO_CLIENT_ID="$CLIENT_ID"
export CLASSROOM_PAGES_TABLE="$PAGES_TABLE"
export CLASSROOM_LESSONS_BUCKET="$LESSONS_BUCKET"
# The share link a teacher hands to a class.
#
# In production this is the STUDENT host — a different origin from the app, which
# is what keeps a lesson's scripts away from her session. Locally the local API
# plays that part, so the link points at :8001, which is still a different origin
# from the SPA on :5174 because an origin includes its port.
export CLASSROOM_PUBLIC_SITE_URL="http://localhost:8001"
# Who may call the API from a browser: the local app, and only it. Mirrors the
# admin-host-only rule in prod — see app_factory.
export CLASSROOM_ALLOWED_ORIGIN="$SPA_ORIGIN"

# ---------------------------------------------------------------------------
# Poetry and node_modules are both dev-setup.sh's job, and it is idempotent, so
# the cheapest correct thing is to delegate rather than reimplement either
# check. node_modules matters as much as the env file: vite is a local binary,
# so without it this script's own `npm run dev` fails the same way `tsc: not
# found` does.
# ---------------------------------------------------------------------------
export PATH="$HOME/.local/bin:$PATH"

# shellcheck source=dev-aws-common.sh
source "$ROOT/classroom/scripts/dev-aws-common.sh"
needs_setup=0
[ -n "$(read_env "$DEV_ENV_FILE" VITE_COGNITO_CLIENT_ID)" ] || needs_setup=1
[ -d classroom/frontend/node_modules ] || needs_setup=1
# Poetry keeps its virtualenv in a cache directory by default, not in the
# project, so `.venv` is the wrong thing to test for and `poetry env info` is
# the right one. It exits non-zero when no environment exists.
command -v poetry >/dev/null 2>&1 || needs_setup=1
(cd classroom/backend && poetry env info --path >/dev/null 2>&1) || needs_setup=1

if [ "$needs_setup" -eq 1 ]; then
  echo "Frontend env, node_modules or the backend environment is missing — running dev-setup.sh first."
  ./classroom/scripts/dev-setup.sh
fi

pids=()
cleanup() {
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT INT TERM

# THE API GATEWAY STAND-IN. **The half of the auth path that is not deployed.**
#
# In prod the gateway verifies the ID token and hands Flask the claims, which is
# why `classroom_core/auth.py` verifies no signature. There is no gateway here,
# so `handlers/local/api/api_dev_server.py` verifies against the pool exported
# above and puts the claims where the gateway would have — and enforces the same
# route split, so `/api/public/*` stays anonymous and GET-only locally too.
echo "Backend  → http://localhost:8001  (pool ${POOL_ID}, table ${PAGES_TABLE})"
echo "Lessons  → http://localhost:8001/lesson/<id>/  (bucket ${LESSONS_BUCKET})"
(cd classroom/backend && poetry run python -m classroom_core.handlers.local.api.api_dev_server) &
pids+=($!)

# 5174, and it has to be exactly that: the app client registers
# `${SPA_ORIGIN}/auth/callback` character for character, so a different port
# fails at the Cognito redirect rather than at startup.
# Vite inlines VITE_* and leaves a variable already in the environment alone,
# so the frontend's values reach it from dev.env without a file next to
# vite.config — and without the bundler seeing anything else in that file.
export_env_prefix "$DEV_ENV_FILE" VITE_
echo "Frontend → $SPA_ORIGIN"
(cd classroom/frontend && npm run dev) &
pids+=($!)

wait
