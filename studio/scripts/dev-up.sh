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

# Credentials must resolve before the API starts; an unauthenticated backend
# fails per-request rather than at boot, which is a slower way to learn the same
# thing. Since August 2026 they are a long-lived access key in
# `~/.aws/credentials` or `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` in the
# environment, and boto3 reads both natively. The export below used to be
# load-bearing — under `aws login` the CLI read a cache boto3 could not see, so
# the API failed with "no EC2 IMDS role found" while `aws sts
# get-caller-identity` happily succeeded. It is kept because it costs nothing
# and still does the right thing for an SSO or credential_process profile.
if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "AWS credentials are not valid. Put an access key in ~/.aws/credentials," >&2
  echo "or set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY. See the root CLAUDE.md." >&2
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
# create.
#
# **THIS MACHINE'S DEV STACK, NOT PROD.** studio used to read `/studio/prod/*`
# here and serve the local API against the live bucket and the live pool. That
# is over (#287): this repo no longer connects to production, the way every
# other service in the monorepo already works.
#
# Running the CLI against prod is a `studio --profile prod <command>` now, and
# it is deliberately not a flag on this script — this one starts a local API
# server, and there is no version of that which should serve production. The
# profile mechanism is `pipeline/src/studio_pipeline/profiles.py`.
#
# The exports below are what the local Flask process reads, and they also feed
# the CLI in this shell: nothing here selects a profile, and with no profile
# selected the environment wins. So `studio` typed in this window drives the
# local API against this machine's stack, exactly as before. An explicit
# `--profile` overrides them and says on stderr that it is doing so — which is
# the case this comment exists for.
#
# The values come from the dev stack's Terraform outputs rather than SSM,
# because SSM holds what the *deploy workflow* wrote and nothing deploys a dev
# stack. `load_dev_stack_outputs` is the same reader `dev-user.sh`,
# `dev-token.sh` and the integration harness use.
# ---------------------------------------------------------------------------
# A subshell, because `dev-aws-common.sh`'s `die` exits and the failure here
# needs a message this script writes rather than that one. Its `log` output goes
# to stderr, so what is captured is exactly the four values.
if ! dev_stack="$(
  # shellcheck source=dev-aws-common.sh
  source "$ROOT/studio/scripts/dev-aws-common.sh"
  load_machine_id false
  load_aws_identity
  load_dev_stack_outputs
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$DEV_POOL_ID" "$DEV_CLIENT_ID" \
    "$DEV_BUCKET" "$DEV_TABLE" "$DEV_CALLBACK_URL" "$DEV_CALLBACK_QUEUE"
)"; then
  echo "Could not read this machine's dev stack." >&2
  echo "  The API verifies every request's token against the dev pool, so it" >&2
  echo "  would 500 on every call. Provision one with:" >&2
  echo "    ./studio/scripts/dev-aws-setup.sh && ./studio/scripts/dev-user.sh" >&2
  exit 1
fi
IFS=$'\t' read -r POOL_ID CLIENT_ID MEDIA_BUCKET CATALOG_TABLE \
  CALLBACK_URL CALLBACK_QUEUE <<<"$dev_stack"

export STUDIO_COGNITO_USER_POOL_ID="$POOL_ID"
export STUDIO_COGNITO_CLIENT_ID="$CLIENT_ID"
# Exported unconditionally now, unlike the SSM version. `config.py`'s defaults
# name PROD resources, so falling through to them is no longer a survivable
# outcome — it is the exact thing this issue removes. `load_dev_stack_outputs`
# refuses an incomplete state, so reaching here means all four are set.
export STUDIO_MEDIA_BUCKET="$MEDIA_BUCKET"
export STUDIO_CATALOG_TABLE="$CATALOG_TABLE"

# ---------------------------------------------------------------------------
# THE CALLBACK PATH, WHICH IS WHY THIS MACHINE HAS AN API GATEWAY IN AWS.
#
# Generation happens in the API now, and a prediction is closed by Replicate
# calling back. Replicate cannot reach `http://localhost:8000` — so a callback
# for a run submitted here lands on this machine's own endpoint, which enqueues
# it, and the consumer started further down drains that queue and closes the run
# **with this checkout**. The webhook path is therefore exercised by the code
# being edited rather than first running for real in production.
#
# Both are optional. A stack applied before this landed has neither, and the
# only consequence is that a finished generation waits for
# `studio runs reconcile <run>` instead of closing itself.
# ---------------------------------------------------------------------------
if [ -n "$CALLBACK_URL" ] && [ -n "$CALLBACK_QUEUE" ]; then
  export STUDIO_WEBHOOK_BASE_URL="$CALLBACK_URL"
  export STUDIO_CALLBACK_QUEUE_URL="$CALLBACK_QUEUE"
else
  echo "This machine's stack has no callback endpoint, so a finished generation" >&2
  echo "  will not close itself. Re-apply with ./studio/scripts/dev-aws-setup.sh," >&2
  echo "  or close runs by hand with: studio runs reconcile <run>" >&2
fi

# The Replicate token. The API holds the provider credential now — the CLI has
# none at all — so it is the local Flask process that needs it, and it is read
# from the same file it has always lived in. In prod the equivalent is an SSM
# SecureString the Lambda reads under its own role; there is deliberately no
# per-machine parameter, because a token is not environment-scoped.
if [ -z "${REPLICATE_API_TOKEN:-}" ] && [ -f "$HOME/.config/andreas-services/studio/dev.env" ]; then
  # shellcheck disable=SC1091
  set -a; source "$HOME/.config/andreas-services/studio/dev.env"; set +a
fi
if [ -z "${REPLICATE_API_TOKEN:-}" ]; then
  echo "REPLICATE_API_TOKEN is not set, so this API cannot submit a generation." >&2
  echo "  Put it in ~/.config/andreas-services/studio/dev.env. Everything else works." >&2
fi

# Where `studio login` and every other CLI call go (#300). Defaults to the
# deployed API; pointed at the Flask process this script is about to start, so
# the CLI drives the local API against this machine's dev stack rather than the
# Lambda.
export STUDIO_API_URL="http://localhost:8000"
# The pool ids the CLI signs in against are already exported above, for the API.
# `studio login` reads the same two, so the CLI and the API it calls cannot
# disagree about which pool a token came from.

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

# THE CONSUMER. **The half of the callback path that is not deployed.**
#
# It long-polls this machine's queue and closes each finished run with the
# working tree — `services/callbacks.py`, the same module the prod worker Lambda
# drives. That is the whole reason receiving and processing were separated: the
# deployed half is a fixed twenty lines that only enqueues, and the half that
# changes runs here, under Flask's own reloader-free process but from the same
# source tree.
#
# Started even when the queue is unset: it says so once and exits 0, which is
# quieter than a conditional here and means one less thing to keep in step.
if [ -n "${STUDIO_CALLBACK_QUEUE_URL:-}" ]; then
  echo "Callbacks → ${STUDIO_CALLBACK_QUEUE_URL##*/}"
fi
(cd studio/backend && poetry run python -m studio_core.handlers.local.consumer.callback_consumer) &
pids+=($!)

echo "Frontend → http://localhost:5173"
(cd studio/frontend && npm run dev) &
pids+=($!)

wait
