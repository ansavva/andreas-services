#!/usr/bin/env bash
# Start the local backend with short-lived credentials exported by the AWS CLI.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dev-aws-common.sh
source "$SCRIPT_DIR/dev-aws-common.sh"

compose_args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) [[ $# -ge 2 ]] || die "--profile requires a value."; AWS_PROFILE_VALUE="$2"; shift ;;
    --region) [[ $# -ge 2 ]] || die "--region requires a value."; AWS_REGION_VALUE="$2"; shift ;;
    --help|-h)
      printf 'Usage: %s [--profile NAME] [--region REGION] [docker-compose-up options]\n' "$0"
      exit 0
      ;;
    *) compose_args+=("$1") ;;
  esac
  shift
done

for command in aws docker jq; do require_command "$command"; done
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required."
export_temporary_aws_credentials
export AWS_DEFAULT_REGION="$AWS_REGION_VALUE"

exec docker compose -f "$HUMBUGG_DIR/backend/docker-compose.yml" up --build "${compose_args[@]}"
