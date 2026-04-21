#!/usr/bin/env bash
# Install the scout pre-commit hook into the repo's .git/hooks/ directory.
# Run once per clone: scout/scripts/install-hooks.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT=$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel)
GIT_COMMON_DIR=$(git -C "${SCRIPT_DIR}" rev-parse --git-common-dir)
HOOKS_DIR="${GIT_COMMON_DIR}/hooks"

cp "${SCRIPT_DIR}/hooks/pre-commit" "${HOOKS_DIR}/pre-commit"
chmod +x "${HOOKS_DIR}/pre-commit"

echo "Installed pre-commit hook -> ${HOOKS_DIR}/pre-commit"
echo "It runs scout unit tests and lint whenever scout/ files are staged."
