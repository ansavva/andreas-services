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

if [ ! -f studio/frontend/.env.local ]; then
  echo "studio/frontend/.env.local is missing — generating it from prod SSM."
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
