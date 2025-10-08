#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BUILD_DIR="${REPO_ROOT}/build/lambda"
LAMBDA_SRC="${REPO_ROOT}/backend/lambda"
REQUIREMENTS_FILE="${REPO_ROOT}/backend/requirements.txt"

rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"

python3 -m pip install --upgrade pip
python3 -m pip install -r "${REQUIREMENTS_FILE}" --target "${BUILD_DIR}"

cp "${LAMBDA_SRC}/"*.py "${BUILD_DIR}/"

echo "Lambda bundle created at ${BUILD_DIR}" 
