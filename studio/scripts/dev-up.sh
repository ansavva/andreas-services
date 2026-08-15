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

if [ ! -f studio/frontend/.env.local ]; then
  echo "studio/frontend/.env.local is missing — copying the example."
  cp studio/frontend/.env.local.example studio/frontend/.env.local
  echo "Fill in the Cognito values, or the app will show 'Auth is not configured'."
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
