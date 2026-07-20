#!/usr/bin/env bash
# Follow the local Dockerized Humbugg backend logs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HUMBUGG_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  printf 'Usage: %s [docker-compose-logs options]\n' "$0"
  printf 'Follows the Humbugg backend logs. Example: %s --tail 200\n' "$0"
  exit 0
fi

command -v docker >/dev/null 2>&1 || {
  printf '[error] Docker is not installed.\n' >&2
  exit 1
}
docker compose version >/dev/null 2>&1 || {
  printf '[error] Docker Compose v2 is required.\n' >&2
  exit 1
}

exec docker compose -f "$HUMBUGG_DIR/backend/docker-compose.yml" logs -f "$@" backend
