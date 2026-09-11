#!/usr/bin/env bash
# Start the website locally: DynamoDB Local, the Python API on :8002 and the
# React Router SSR dev server on :5175 — every process fed from the one
# per-machine env file, ~/.config/andreas-services/website/dev.env.
#
# The website has no per-machine AWS stack, so nothing generates that file: it
# is laid out from website/dev.env.sample — values yours, layout the sample's.
# `WEBSITE_DEV_ENV_FILE` overrides the location. It sits outside the repo
# because ignored files vanish on `git clean -fdx` and never exist in a fresh
# worktree, and it holds the Cognito client secret and the session secret.
#
# Every key is exported, unprefixed names included: the SSR server reads
# WEBSITE_API_URL, COGNITO_* and SESSION_SECRET from process.env at request
# time, the API reads WEBSITE_INTAKE_TABLE and KIT_*, and Vite inlines only
# VITE_* into the client bundle — a shell variable beats a .env file for all
# three, which is why no file needs to sit next to package.json.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WEBSITE_DIR="$ROOT/website"
DEV_ENV_FILE="${WEBSITE_DEV_ENV_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/andreas-services/website/dev.env}"

log()  { printf '\033[36m[website]\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[33m[website]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m[website]\033[0m %s\n' "$*" >&2; exit 1; }

RUN_FRONTEND=0; RUN_BACKEND=0; SERVE_BUILD=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --frontend) RUN_FRONTEND=1 ;;
    --backend) RUN_BACKEND=1 ;;
    --serve-build) SERVE_BUILD=1 ;;   # `npm run start` on an existing build, :3000
    --help|-h)
      printf 'Usage: %s [--frontend] [--backend] [--serve-build]\n' "$0"
      printf 'No flag starts DynamoDB Local, the API and the SSR dev server together.\n'
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done
if [[ "$RUN_FRONTEND" -eq 0 && "$RUN_BACKEND" -eq 0 && "$SERVE_BUILD" -eq 0 ]]; then
  RUN_FRONTEND=1; RUN_BACKEND=1
fi

# Render the file in the sample's layout on every run: each `KEY=` line of the
# sample takes the file's value when it has one, the sample's otherwise, so a
# new key gets its slot without a hand merge; keys the sample does not know are
# carried over at the end. Values are never lost and never overwritten.
read_env() { awk -v key="$2" -F= '$1 == key { sub("^" key "=", ""); print; exit }' "$1" 2>/dev/null; }
mkdir -p "$(dirname "$DEV_ENV_FILE")"
chmod 700 "$(dirname "$DEV_ENV_FILE")"
[[ -f "$DEV_ENV_FILE" ]] || warn "creating $DEV_ENV_FILE from website/dev.env.sample — fill in the values that matter to you."
previous="$(mktemp)"; chmod 600 "$previous"
cat "$DEV_ENV_FILE" > "$previous" 2>/dev/null || true
rendered="$(mktemp)"; chmod 600 "$rendered"
written=""
while IFS= read -r line; do
  if [[ "$line" =~ ^#?([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
    key="${BASH_REMATCH[1]}"
    if grep -Eq "^${key}=" "$previous"; then line="$key=$(read_env "$previous" "$key")"; fi
    written="$written $key"
  fi
  printf '%s\n' "$line" >> "$rendered"
done < "$WEBSITE_DIR/dev.env.sample"
leftover="$(awk -F= -v written=" $written " '
  /^[A-Za-z_][A-Za-z0-9_]*=/ && index(written, " " $1 " ") == 0 { print }
' "$previous" | sort)"
if [[ -n "$leftover" ]]; then
  printf '\n# ---- not in the sample; carried over as found --------------------------------\n%s\n' "$leftover" >> "$rendered"
fi
rm -f "$previous"
mv "$rendered" "$DEV_ENV_FILE"

# Export every KEY=value line; comments and blanks skipped. Not `source`d: the
# secrets in it are not all shell-safe.
while IFS= read -r line; do
  [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue
  export "${BASH_REMATCH[1]}=${BASH_REMATCH[2]}"
done < "$DEV_ENV_FILE"
export PATH="/opt/homebrew/opt/node@20/bin:$HOME/.local/bin:$PATH"

pids=()
cleanup() { for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM

if [[ "$RUN_BACKEND" -eq 1 ]]; then
  command -v docker >/dev/null 2>&1 || die "Docker is required for DynamoDB Local."
  command -v poetry >/dev/null 2>&1 || die "Poetry is required for the API. Run: uv tool install poetry"
  log "DynamoDB Local → localhost:8001"
  docker compose -f "$WEBSITE_DIR/backend/docker-compose.yml" up -d dynamodb >/dev/null
  log "API → http://localhost:8002"
  (cd "$WEBSITE_DIR/backend" && poetry run python -m website_core.handlers.local.api.api_dev_server) &
  pids+=($!)
fi
if [[ "$RUN_FRONTEND" -eq 1 ]]; then
  [[ -d "$WEBSITE_DIR/frontend/node_modules" ]] ||
    die "frontend/node_modules missing. Run: NODE_AUTH_TOKEN=\$(gh auth token) npm --prefix website/frontend ci"
  log "SSR dev server → http://localhost:5175"
  (cd "$WEBSITE_DIR/frontend" && npm run dev) &
  pids+=($!)
fi
if [[ "$SERVE_BUILD" -eq 1 ]]; then
  [[ -f "$WEBSITE_DIR/frontend/build/server/index.js" ]] ||
    die "No build to serve. Run: npm --prefix website/frontend run build"
  log "Production build → http://localhost:3000"
  (cd "$WEBSITE_DIR/frontend" && npm run start) &
  pids+=($!)
fi

wait
