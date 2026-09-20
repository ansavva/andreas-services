#!/usr/bin/env bash
# Tear down studio's Wan 2.2 serverless endpoint: the endpoint, then its
# template. The network volume is LEFT, deliberately — it holds 64 GB of
# weights that took a pod and a download to put there, and it costs about
# $7/month at 100 GB. `--volume` removes that too.
#
# After this, a run on `wan-2.2-i2v-studio` fails at submit with a 404 from
# Runpod and is handed back as a draft; nothing else in studio notices.
#
# Usage:
#   ./studio/scripts/runpod-endpoint-down.sh            # endpoint + template
#   ./studio/scripts/runpod-endpoint-down.sh --volume   # and the weights
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=runpod-common.sh
source "$SCRIPT_DIR/runpod-common.sh"

WITH_VOLUME=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --volume) WITH_VOLUME=1 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

ENDPOINT_ID="$(runpod_endpoint_id)"
if [ -n "$ENDPOINT_ID" ]; then
  # Workers first: an endpoint with a worker still up refuses the delete.
  runpod_rest PATCH "/endpoints/$ENDPOINT_ID" '{"workersMin":0,"workersMax":0}' >/dev/null || true
  runpod_rest DELETE "/endpoints/$ENDPOINT_ID" >/dev/null
  echo "deleted endpoint $ENDPOINT_ID"
else
  echo "no endpoint named $WAN22_ENDPOINT_NAME"
fi

TEMPLATE_ID="$(runpod_template_id)"
if [ -n "$TEMPLATE_ID" ]; then
  runpod_rest DELETE "/templates/$TEMPLATE_ID" >/dev/null
  echo "deleted template $TEMPLATE_ID"
fi

VOLUME_ID="$(runpod_volume_id)"
if [ "$WITH_VOLUME" = 1 ] && [ -n "$VOLUME_ID" ]; then
  runpod_rest DELETE "/networkvolumes/$VOLUME_ID" >/dev/null
  echo "deleted volume $VOLUME_ID"
elif [ -n "$VOLUME_ID" ]; then
  echo "volume $VOLUME_ID kept (100 GB, about \$7/month); --volume removes it"
fi

echo "pods still running (should be none of ours):"
runpod_rest GET /pods | python3 -c 'import json,sys; [print(" ", p["id"], p.get("name"), p.get("desiredStatus")) for p in json.load(sys.stdin) or []] or print("  none")'
echo "balance: \$$(runpod_balance)"
