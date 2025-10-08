#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

IMAGE_NAME="${IMAGE_NAME:-events-gmail-ingest}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
DOCKERFILE="backend/Dockerfile"

cd "${REPO_ROOT}"

echo "Building ${IMAGE_NAME}:${IMAGE_TAG} using ${DOCKERFILE}"
docker build -f "${DOCKERFILE}" -t "${IMAGE_NAME}:${IMAGE_TAG}" .

echo "Image built: ${IMAGE_NAME}:${IMAGE_TAG}"
