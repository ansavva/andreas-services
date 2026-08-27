#!/usr/bin/env bash
#
# Both integration suites, against this machine's dev stack.
#
# **These never run in CI.** `studio-pr.yml` validates only and never writes to
# AWS; that is a repo-wide rule and this is not the exception to it. What runs
# here writes to a real account — a real table, a real bucket, a real Cognito
# pool — which is why both trees are skipped at collection without
# `STUDIO_INTEGRATION=1` and why that flag is set here and nowhere else.
#
#     backend/tests/integration/    the Flask app against real S3, DynamoDB and
#                                   Cognito. Existed already.
#     pipeline/tests/integration/   the `studio` CLI against the running API and
#                                   that same stack. NEW: every other test of the
#                                   CLI talks to `tests/support/fake_api.py`, and
#                                   nothing had proved the real API answers the
#                                   way that fake claims.
#
# Nothing here bills. The CLI subprocesses run with `STUDIO_REPLICATE_MODE=fake`
# and both suites block the provider hosts at the socket.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STUDIO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=./dev-aws-common.sh
source "$SCRIPT_DIR/dev-aws-common.sh"

export STUDIO_INTEGRATION=1

only="${1:-both}"

if [[ "$only" == "both" || "$only" == "pipeline" ]]; then
  # The pipeline suite needs the API up, because the CLI reaches ONLY the API.
  if ! curl -fsS --max-time 3 http://localhost:8000/api/health >/dev/null 2>&1; then
    die "the local API is not answering on :8000. Start it with scripts/dev-up.sh."
  fi
  log "pipeline — the CLI against the API and the dev stack"
  ( cd "$STUDIO_DIR/pipeline" && uv run pytest tests/integration -q )
fi

if [[ "$only" == "both" || "$only" == "backend" ]]; then
  log "backend — the app against real S3, DynamoDB and Cognito"
  ( cd "$STUDIO_DIR/backend" && poetry run pytest tests/integration -q )
fi

ok "Integration suites passed."
