#!/usr/bin/env bash
# Run scout unit tests and frontend lint locally.
# Mirrors what the CI lint-unit-build job does.
#
# Usage:
#   ./scripts/test-unit.sh            # run everything
#   ./scripts/test-unit.sh --python   # Python unit tests only
#   ./scripts/test-unit.sh --frontend # frontend lint only
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCOUT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RUN_PYTHON=true
RUN_FRONTEND=true

for arg in "$@"; do
    case $arg in
        --python)   RUN_FRONTEND=false ;;
        --frontend) RUN_PYTHON=false ;;
        *) echo "Unknown option: $arg"; exit 1 ;;
    esac
done

pass() { echo "[PASS] $*"; }
fail() { echo "[FAIL] $*"; exit 1; }

run_poetry_tests() {
    local name="$1"
    local dir="$2"

    if [[ ! -d "${dir}" ]]; then
        echo "[SKIP] ${name} tests (${dir} does not exist)"
        return 0
    fi

    echo "--- ${name} unit tests ---"
    (
        cd "${dir}"
        poetry install --with dev --no-root --no-interaction --no-ansi -q
        poetry run pytest tests/ -v
    ) || fail "${name} tests"
    pass "${name} tests"
}

if [[ "$RUN_PYTHON" == "true" ]]; then
    run_poetry_tests "events-api" "${SCOUT_ROOT}/backend/events-api"

    echo
    run_poetry_tests "email-processor" "${SCOUT_ROOT}/backend/email-processor"
fi

if [[ "$RUN_FRONTEND" == "true" ]]; then
    echo
    echo "--- frontend lint ---"
    (
        cd "${SCOUT_ROOT}/frontend"
        [[ ! -d node_modules ]] && npm install --silent
        npm run lint
    ) || fail "frontend lint"
    pass "frontend lint"
fi

echo
echo "All checks passed."
