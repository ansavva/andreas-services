#!/usr/bin/env bash
# Start the backend, frontend, and Stripe webhook listener as one local development session.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dev-aws-common.sh
source "$SCRIPT_DIR/dev-aws-common.sh"

FORWARD_TO="${STRIPE_WEBHOOK_FORWARD_TO:-localhost:5001/api/billing/stripe/webhook}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) [[ $# -ge 2 ]] || die "--profile requires a value."; AWS_PROFILE_VALUE="$2"; shift ;;
    --region) [[ $# -ge 2 ]] || die "--region requires a value."; AWS_REGION_VALUE="$2"; shift ;;
    --forward-to) [[ $# -ge 2 ]] || die "--forward-to requires a value."; FORWARD_TO="$2"; shift ;;
    --help|-h)
      printf 'Usage: %s [--profile NAME] [--region REGION] [--forward-to URL]\n' "$0"
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done

for command in aws docker jq npm stripe; do require_command "$command"; done

backend_env="$HUMBUGG_DIR/backend/.env"
[[ -f "$backend_env" ]] ||
  die "Missing $backend_env. Run ./humbugg/scripts/dev-aws-setup.sh first."

webhook_secret="$(stripe listen --print-secret --skip-update)" ||
  die "Stripe could not retrieve its local webhook signing secret. Run 'stripe login' first."
[[ "$webhook_secret" == whsec_* ]] ||
  die "Stripe returned an invalid webhook signing secret. Run 'stripe login' and try again."

upsert_env() {
  local file="$1" key="$2" value="$3" temp
  temp="$(mktemp)"
  awk -v key="$key" -v value="$value" '
    BEGIN { found = 0 }
    $0 ~ "^" key "=" {
      if (!found) print key "=" value
      found = 1
      next
    }
    { print }
    END { if (!found) print key "=" value }
  ' "$file" > "$temp"
  chmod 600 "$temp"
  mv "$temp" "$file"
}

upsert_env "$backend_env" HUMBUGG_STRIPE_WEBHOOK_SECRET "$webhook_secret"
unset webhook_secret
ok "Updated the ignored backend environment with the current Stripe CLI signing secret."

pids=()
names=()
cleaning_up=0

cleanup() {
  local pid
  [[ "$cleaning_up" -eq 0 ]] || return
  cleaning_up=1
  trap - EXIT INT TERM
  printf '\n'
  log "Stopping local development services..."
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  for pid in "${pids[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
}

trap cleanup EXIT
trap 'exit 130' INT TERM

start_service() {
  local name="$1"
  shift
  log "Starting $name..."
  "$@" &
  pids+=("$!")
  names+=("$name")
}

start_service backend "$SCRIPT_DIR/dev-up-backend.sh" \
  --profile "$AWS_PROFILE_VALUE" --region "$AWS_REGION_VALUE"
start_service frontend "$SCRIPT_DIR/dev-up-frontend.sh"
start_service stripe "$SCRIPT_DIR/dev-up-stripe.sh" --forward-to "$FORWARD_TO" --skip-update

ok "Humbugg local development is starting. Press Ctrl+C to stop everything."

while true; do
  for index in "${!pids[@]}"; do
    pid="${pids[$index]}"
    if ! kill -0 "$pid" 2>/dev/null; then
      set +e
      wait "$pid"
      status=$?
      set -e
      [[ "$status" -eq 0 ]] || warn "${names[$index]} exited with status $status."
      exit "$status"
    fi
  done
  sleep 1
done
