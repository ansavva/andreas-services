#!/usr/bin/env bash
set -euo pipefail

# Idempotently provisions the Humbugg Plus test product/price. Authentication is
# delegated to the Stripe CLI; no key is accepted as an argument or written to disk.
command -v stripe >/dev/null || { echo "Install the Stripe CLI first." >&2; exit 1; }
command -v jq >/dev/null || { echo "Install jq first." >&2; exit 1; }

product_id="$(
  stripe products list --limit 100 |
    jq -r '.data[] | select(.metadata.humbugg_plan == "plus") | .id' |
    head -n 1
)"
if [[ -z "$product_id" ]]; then
  product_id="$(
    stripe products create \
      --name "Humbugg Plus" \
      -d "metadata[humbugg_plan]=plus" \
      -d "metadata[managed_by]=andreas-services" |
      jq -r '.id'
  )"
fi

price_id="$(
  stripe prices list --product "$product_id" --active true --type one_time --limit 100 |
    jq -r '.data[] | select(.currency == "usd" and .unit_amount == 1200) | .id' |
    head -n 1
)"
if [[ -z "$price_id" ]]; then
  price_id="$(
    stripe prices create \
      --product "$product_id" \
      --currency usd \
      --unit-amount 1200 \
      -d "metadata[humbugg_plan]=plus" |
      jq -r '.id'
  )"
fi

verified="$(
  stripe prices retrieve "$price_id" |
    jq -e '.livemode == false and .active == true and .currency == "usd" and .unit_amount == 1200 and .type == "one_time"'
)"
[[ "$verified" == "true" ]]

echo "HUMBUGG_PLUS_PRODUCT_ID=$product_id"
echo "HUMBUGG_PLUS_PRICE_ID=$price_id"
