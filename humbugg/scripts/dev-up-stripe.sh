#!/usr/bin/env bash
# Forward the Stripe test webhook events handled by Humbugg to the local backend.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dev-aws-common.sh
source "$SCRIPT_DIR/dev-aws-common.sh"

FORWARD_TO="${STRIPE_WEBHOOK_FORWARD_TO:-localhost:5001/api/billing/stripe/webhook}"
EVENTS="checkout.session.completed,checkout.session.async_payment_succeeded,checkout.session.async_payment_failed,checkout.session.expired,charge.succeeded,charge.refunded"
stripe_args=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --forward-to)
      [[ $# -ge 2 ]] || die "--forward-to requires a value."
      FORWARD_TO="$2"
      shift
      ;;
    --help|-h)
      printf 'Usage: %s [--forward-to URL] [stripe-listen options]\n' "$0"
      printf 'Default endpoint: %s\n' "$FORWARD_TO"
      printf 'Events: %s\n' "$EVENTS"
      exit 0
      ;;
    *) stripe_args+=("$1") ;;
  esac
  shift
done

require_command stripe

log "Forwarding Stripe test events to $FORWARD_TO"
log "Copy the displayed whsec_ signing secret into HUMBUGG_STRIPE_WEBHOOK_SECRET, then restart the backend."

exec stripe listen \
  --events "$EVENTS" \
  --forward-to "$FORWARD_TO" \
  "${stripe_args[@]}"
