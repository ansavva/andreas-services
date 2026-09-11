#!/usr/bin/env bash
# Start storybook locally: DynamoDB Local on :8004, the Flask API on :8003 and
# the Vite dev server on :5177 — every process fed from the one per-machine
# env file, ~/.config/andreas-services/storybook/dev.env.
#
# Storybook has no per-machine AWS stack, so nothing generates that file: it
# is laid out from storybook/dev.env.sample — values yours, layout the
# sample's. `STORYBOOK_DEV_ENV_FILE` overrides the location. It sits outside
# the repo because ignored files vanish on `git clean -fdx` and never exist in
# a fresh worktree, and it holds provider tokens.
#
# Every key is exported: the API reads AWS_COGNITO_*, S3_BUCKET_NAME and the
# provider tokens from the environment, and Vite inlines only VITE_* into the
# client bundle — a shell variable beats a .env file for both, which is why no
# file needs to sit next to package.json.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STORYBOOK_DIR="$ROOT/storybook"
DEV_ENV_FILE="${STORYBOOK_DEV_ENV_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/andreas-services/storybook/dev.env}"

log()  { printf '\033[36m[storybook]\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[33m[storybook]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m[storybook]\033[0m %s\n' "$*" >&2; exit 1; }

RUN_FRONTEND=0; RUN_BACKEND=0; RUN_WORKER=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --frontend) RUN_FRONTEND=1 ;;
    --backend) RUN_BACKEND=1 ;;
    --worker) RUN_WORKER=1 ;;   # the image-normalization SQS poller; needs IMAGE_UPLOAD_QUEUE_URL
    --help|-h)
      printf 'Usage: %s [--frontend] [--backend] [--worker]\n' "$0"
      printf 'No flag starts DynamoDB Local, the API and the Vite dev server together.\n'
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done
if [[ "$RUN_FRONTEND" -eq 0 && "$RUN_BACKEND" -eq 0 && "$RUN_WORKER" -eq 0 ]]; then
  RUN_FRONTEND=1; RUN_BACKEND=1
fi

# Render the file in the sample's layout on every run: each `KEY=` line of the
# sample takes the file's value when it has one, the sample's otherwise, so a
# new key gets its slot without a hand merge; keys the sample does not know are
# carried over at the end. Values are never lost and never overwritten.
read_env() { awk -v key="$2" -F= '$1 == key { sub("^" key "=", ""); print; exit }' "$1" 2>/dev/null; }
mkdir -p "$(dirname "$DEV_ENV_FILE")"
chmod 700 "$(dirname "$DEV_ENV_FILE")"
[[ -f "$DEV_ENV_FILE" ]] || warn "creating $DEV_ENV_FILE from storybook/dev.env.sample — fill in the values that matter to you."
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
done < "$STORYBOOK_DIR/dev.env.sample"
leftover="$(awk -F= -v written=" $written " '
  /^[A-Za-z_][A-Za-z0-9_]*=/ && index(written, " " $1 " ") == 0 { print }
' "$previous" | sort)"
if [[ -n "$leftover" ]]; then
  printf '\n# ---- not in the sample; carried over as found --------------------------------\n%s\n' "$leftover" >> "$rendered"
fi
rm -f "$previous"
mv "$rendered" "$DEV_ENV_FILE"

# Export every KEY=value line; comments and blanks skipped. Not `source`d: the
# tokens in it are not all shell-safe.
while IFS= read -r line; do
  [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue
  export "${BASH_REMATCH[1]}=${BASH_REMATCH[2]}"
done < "$DEV_ENV_FILE"
export PATH="$HOME/.local/bin:$PATH"

pids=()
cleanup() { for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM

if [[ "$RUN_BACKEND" -eq 1 || "$RUN_WORKER" -eq 1 ]]; then
  command -v poetry >/dev/null 2>&1 || die "Poetry is required for the API. Run: uv tool install poetry"
fi
if [[ "$RUN_BACKEND" -eq 1 ]]; then
  command -v docker >/dev/null 2>&1 || die "Docker is required for DynamoDB Local."
  log "DynamoDB Local → localhost:8004"
  docker compose -f "$STORYBOOK_DIR/backend/docker-compose.yml" up -d dynamodb >/dev/null
  log "API → http://localhost:8003"
  (cd "$STORYBOOK_DIR/backend" && poetry run python -m storybook_core.handlers.local.api.api_dev_server) &
  pids+=($!)
fi
if [[ "$RUN_WORKER" -eq 1 ]]; then
  [[ -n "${IMAGE_UPLOAD_QUEUE_URL:-}" ]] || die "IMAGE_UPLOAD_QUEUE_URL is not set in $DEV_ENV_FILE."
  log "Image worker → polling $IMAGE_UPLOAD_QUEUE_URL"
  (cd "$STORYBOOK_DIR/backend" && poetry run python -m storybook_core.handlers.local.jobs.poll_image_normalization_handler) &
  pids+=($!)
fi
if [[ "$RUN_FRONTEND" -eq 1 ]]; then
  [[ -d "$STORYBOOK_DIR/frontend/storybook-ui/node_modules" ]] ||
    die "frontend/storybook-ui/node_modules missing. Run: npm --prefix storybook/frontend/storybook-ui install --legacy-peer-deps"
  log "Vite dev server → http://localhost:5177"
  (cd "$STORYBOOK_DIR/frontend/storybook-ui" && npm run dev) &
  pids+=($!)
fi

wait
