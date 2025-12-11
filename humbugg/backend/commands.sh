#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME=humbugg-backend
AWS_REGION=${AWS_REGION:-us-east-1}
AWS_ACCOUNT=${AWS_ACCOUNT:-$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")}
ECR_REPO=${ECR_REPO:-$IMAGE_NAME}
PORT=${PORT:-5001}

build_local() {
  docker buildx build --platform linux/amd64 -t "$IMAGE_NAME" .
}

run_local() {
  docker run --rm -p ${PORT}:${PORT} "$IMAGE_NAME"
}

push_ecr() {
  if [[ -z "$AWS_ACCOUNT" ]]; then
    echo "AWS credentials not configured" >&2
    exit 1
  fi
  aws ecr describe-repositories --repository-names "$ECR_REPO" >/dev/null 2>&1 || \
    aws ecr create-repository --repository-name "$ECR_REPO" >/dev/null
  aws ecr get-login-password --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin "$AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com"
  docker tag "$IMAGE_NAME:latest" "$AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest"
  docker push "$AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest"
}

case "${1:-build}" in
  build)
    build_local
    ;;
  run)
    run_local
    ;;
  push)
    build_local
    push_ecr
    ;;
  *)
    echo "Usage: $0 {build|run|push}" >&2
    exit 1
    ;;
esac
