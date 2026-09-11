#!/usr/bin/env bash
set -euo pipefail

# Idempotently provisions the Humbugg Plus product/price. Authentication is
# delegated to the Stripe CLI; no key is accepted as an argument or written to disk.
#
# --mode test (default): every `stripe` call runs against the CLI's default
#   (test-mode) context, and the resulting price must have `livemode == false`.
# --mode live: every `stripe` call carries `--live`, and the resulting price must
#   have `livemode == true`. The CLI here is only ever logged in for test — do not
#   run this in live mode until issue #159 (merchant-identity review) is closed.
#
# Prints only product/price ids, never keys, in either mode.

MODE="test"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      [[ $# -ge 2 ]] || { echo "--mode requires a value (test|live)." >&2; exit 1; }
      MODE="$2"
      shift
      ;;
    --help|-h)
      printf 'Usage: %s [--mode test|live]\n' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
  shift
done

if [[ "$MODE" != "test" && "$MODE" != "live" ]]; then
  echo "--mode must be 'test' or 'live', got '$MODE'." >&2
  exit 1
fi

command -v stripe >/dev/null || { echo "Install the Stripe CLI first." >&2; exit 1; }
command -v jq >/dev/null || { echo "Install jq first." >&2; exit 1; }

live_flag=()
expect_livemode="false"
if [[ "$MODE" == "live" ]]; then
  live_flag=(--live)
  expect_livemode="true"
fi

product_id="$(
  stripe products list "${live_flag[@]}" --limit 100 |
    jq -r '.data[] | select(.metadata.humbugg_plan == "plus") | .id' |
    head -n 1
)"
if [[ -z "$product_id" ]]; then
  product_id="$(
    stripe products create "${live_flag[@]}" \
      --name "Humbugg Plus" \
      -d "metadata[humbugg_plan]=plus" \
      -d "metadata[managed_by]=andreas-services" |
      jq -r '.id'
  )"
fi

price_id="$(
  stripe prices list "${live_flag[@]}" --product "$product_id" --active=true --type one_time --limit 100 |
    jq -r '.data[] | select(.currency == "usd" and .unit_amount == 1200) | .id' |
    head -n 1
)"
if [[ -z "$price_id" ]]; then
  price_id="$(
    stripe prices create "${live_flag[@]}" \
      --product "$product_id" \
      --currency usd \
      --unit-amount 1200 \
      -d "metadata[humbugg_plan]=plus" |
      jq -r '.id'
  )"
fi

verified="$(
  stripe prices retrieve "${live_flag[@]}" "$price_id" |
    jq -e --argjson expect_livemode "$expect_livemode" \
      '.livemode == $expect_livemode and .active == true and .currency == "usd" and .unit_amount == 1200 and .type == "one_time"'
)"
[[ "$verified" == "true" ]]

echo "HUMBUGG_PLUS_PRODUCT_ID=$product_id"
echo "HUMBUGG_PLUS_PRICE_ID=$price_id"
