#!/bin/bash
# SessionStart hook: project-level setup that runs every session (including
# resumed) in both local and cloud environments.
#
# The shared CLI toolchain (aws, gh, tflint, terraform, ...) is owned by
# scripts/dev-setup.sh in this repo rather than by the cloud environment's Setup
# script, so it is versioned with the code and identical on a laptop and in a
# cloud session. dev-setup.sh short-circuits on `command -v` per tool and only
# reaches for Homebrew when something is genuinely missing, so when the image
# already ships these CLIs this costs a handful of lookups.
set -euo pipefail

REPO="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

# Per-session env vars. Subsequent Bash tool calls inherit these.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "AWS_DEFAULT_REGION=us-east-1"
    echo "AWS_PAGER="
  } >> "$CLAUDE_ENV_FILE"
fi

# studio's generation skills run LOCALLY, inside Claude, on this machine — they
# are the one part of this repo that never deploys. They need `uv` on PATH, so
# this runs before the cloud-only early exit below rather than after it.
# dev-setup.sh is idempotent and cheap once uv is installed and the caches are
# warm. Non-fatal: a failed setup should degrade the studio skills, not block
# the session.
if [ -f "$REPO/studio/scripts/dev-setup.sh" ]; then
  bash "$REPO/studio/scripts/dev-setup.sh" >&2 || true
fi

# Cloud-only steps below. Local dev environments already have these set up.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Shared CLI toolchain. Non-fatal: a missing tool should degrade the session,
# not block it. The steps below depend on what this installs, so it runs first.
if [ -f "$REPO/scripts/dev-setup.sh" ]; then
  bash "$REPO/scripts/dev-setup.sh" >&2 || true
fi

# pre-commit: install the git hook and pre-download hook environments so
# `pre-commit run` is instant when Claude wants to verify a change.
if command -v pre-commit &>/dev/null && [ -f "$REPO/.pre-commit-config.yaml" ]; then
  (cd "$REPO" && pre-commit install >&2) || true
  (cd "$REPO" && pre-commit install-hooks >&2) || true
fi

# tflint ruleset plugins. Idempotent and fast once the plugin cache is warm.
if command -v tflint &>/dev/null && [ -f "$REPO/.tflint.hcl" ]; then
  tflint --init --config "$REPO/.tflint.hcl" >&2 || true
fi

# Poetry installs for each backend so pytest/ruff are ready immediately.
# Failures are non-fatal — a broken install shouldn't block the session.
if command -v poetry &>/dev/null; then
  for d in storybook/backend humbugg/backend scout/backend/events-api; do
    [ -f "$REPO/$d/pyproject.toml" ] || continue
    echo "Installing $d deps..." >&2
    (cd "$REPO/$d" && poetry install --with dev --no-root --no-interaction --no-ansi -q) >&2 || true
  done
fi
