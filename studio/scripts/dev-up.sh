#!/usr/bin/env bash
#
# Start the studio backend and frontend together for local development.
#
# Unlike the other services there is no local emulator to point at: the whole
# point of this API is reading a real S3 bucket, so local dev uses real
# read-only AWS credentials.
#
#   ./studio/scripts/dev-up.sh
#
# Backend on :8000, frontend on :5173. Ctrl+C stops both.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# `aws login` writes a cache only the AWS CLI reads; boto3 needs the credentials
# in the environment. Exporting here is what stops the API from failing with
# "no EC2 IMDS role found" while `aws sts get-caller-identity` happily succeeds.
# See "Running Terraform locally?" in the root CLAUDE.md — same split.
if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "AWS credentials are not valid. Run 'aws login' first." >&2
  exit 1
fi
eval "$(aws configure export-credentials --format env)"

export AWS_DEFAULT_REGION="${AWS_REGION:-us-east-1}"
export STUDIO_ALLOWED_ORIGIN="http://localhost:5173"

# ---------------------------------------------------------------------------
# What the API now needs before it can answer anything at all.
#
# The `before_request` hook identifies the caller on every request, so the two
# Cognito values stopped being optional the day it landed. `config.py` gives
# neither a default on purpose — a pool id that is merely *wrong* rejects every
# caller, and one naming a different pool would admit that pool's users, so
# there is no value worth guessing — which means an unset one is a `ConfigError`
# and a 500 on the first request, not a warning at startup. Without these
# exports the whole local API answers 500 before it reaches a route.
#
# Read from SSM, the same parameters and by the same method `dev-setup.sh`
# already uses to write `frontend/.env.local`. They are written there by the
# deploy workflow from Terraform's outputs, so they cannot drift from what is
# deployed — and the frontend signing in against one pool while the backend
# verifies against another is precisely the drift a hardcoded value would
# create. This is the prod pool and the prod table: local points at prod for
# studio, deliberately. See dev-setup.sh.
#
# `|| true` inside the helper because `set -e` would otherwise abort the script
# on a missing parameter with no message, which is the opposite of the intent.
# ---------------------------------------------------------------------------
ssm() { aws ssm get-parameter --name "$1" --query Parameter.Value --output text 2>/dev/null || true; }

POOL_ID="$(ssm /studio/prod/cognito-user-pool-id)"
CLIENT_ID="$(ssm /studio/prod/cognito-client-id)"
if [ -z "$POOL_ID" ] || [ -z "$CLIENT_ID" ]; then
  echo "Could not read the Cognito values from SSM (/studio/prod/cognito-*)." >&2
  echo "  The API verifies every request's token against them, so it would 500" >&2
  echo "  on every call. Has studio been deployed?" >&2
  exit 1
fi
export STUDIO_COGNITO_USER_POOL_ID="$POOL_ID"
export STUDIO_COGNITO_CLIENT_ID="$CLIENT_ID"

# The bucket and the table are exported only when SSM answers. Both have a
# prod-matching default in `config.py`, so a missing parameter is survivable
# where a missing pool id is not — and repeating either name here would be a
# second copy to keep in step with that default for no gain. (There is no
# `/studio/prod/catalog-table` parameter yet; this picks it up the day the
# deploy workflow writes one, and falls through to the default until then.)
#
# Spelled as `if` blocks and not `[ -n "$X" ] && export ...`: under `set -e` a
# one-liner whose test fails is a failed command, and the script would exit
# silently on exactly the case it is meant to tolerate.
MEDIA_BUCKET="$(ssm /studio/prod/media-bucket)"
if [ -n "$MEDIA_BUCKET" ]; then
  export STUDIO_MEDIA_BUCKET="$MEDIA_BUCKET"
fi
CATALOG_TABLE="$(ssm /studio/prod/catalog-table)"
if [ -n "$CATALOG_TABLE" ]; then
  export STUDIO_CATALOG_TABLE="$CATALOG_TABLE"
fi

# ---------------------------------------------------------------------------
# Poetry, which nothing else installs.
#
# studio has two toolchains because it is two halves. The pipeline is uv (see
# dev-setup.sh, which installs it); the backend is Poetry, pinned to 2.2.1 in
# both `studio-pr.yml` and `backend/Dockerfile`. dev-setup.sh deliberately
# covers only the local half and says so — "the deployed half is built by CI and
# needs nothing from here" — but this script runs the backend, so Poetry is a
# prerequisite of local dev that neither script owned. On a machine that had
# never built the image the result was `poetry: command not found` from a script
# whose whole job is starting the app.
#
# Installed via uv, which dev-setup.sh has already guaranteed, at the version CI
# and the Dockerfile use so a local test failure means the same thing there.
# ---------------------------------------------------------------------------
export PATH="$HOME/.local/bin:$PATH"

if ! command -v poetry >/dev/null 2>&1; then
  if command -v uv >/dev/null 2>&1; then
    echo "Poetry is missing — installing 2.2.1 (the version CI and the image pin)."
    uv tool install poetry==2.2.1
  else
    echo "Poetry and uv are both missing. Run ./studio/scripts/dev-setup.sh first." >&2
    exit 1
  fi
fi

# `--no-root` because the backend is not a package: the Dockerfile copies
# `studio_core` in rather than installing it. Cheap to re-run, so it is not
# guarded — Poetry resolves from the lockfile and does nothing when satisfied.
(cd studio/backend && poetry install --no-root --no-interaction)

# Both of these are dev-setup.sh's job, and it is idempotent, so the cheapest
# correct thing is to delegate rather than reimplement either check. node_modules
# matters as much as the env file: vite is a local binary, so without it this
# script's own `npm run dev` fails the same way `tsc: not found` does.
if [ ! -f studio/frontend/.env.local ] || [ ! -d studio/frontend/node_modules ]; then
  echo "Frontend env or node_modules missing — running dev-setup.sh first."
  ./studio/scripts/dev-setup.sh
fi

pids=()
cleanup() {
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT INT TERM

echo "Backend  → http://localhost:8000"
(cd studio/backend && poetry run python -m studio_core.handlers.local.api.api_dev_server) &
pids+=($!)

echo "Frontend → http://localhost:5173"
(cd studio/frontend && npm run dev) &
pids+=($!)

wait
