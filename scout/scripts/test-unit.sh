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

if [[ "$RUN_PYTHON" == "true" ]]; then
    echo "--- events-api unit tests ---"
    (
        cd "${SCOUT_ROOT}/lambda/events-api"
        pip3 install -q -r requirements-test.txt
        python3 -m pytest tests/ -v
    ) || fail "events-api tests"
    pass "events-api tests"

    echo
    echo "--- email-processor unit tests ---"
    (
        cd "${SCOUT_ROOT}/lambda/email-processor"
        pip3 install -q -r requirements-test.txt
        python3 -m pytest tests/ -v
    ) || fail "email-processor tests"
    pass "email-processor tests"
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
