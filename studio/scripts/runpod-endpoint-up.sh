#!/usr/bin/env bash
# Create (or converge) studio's Wan 2.2 serverless endpoint on Runpod.
#
# What it makes, in order: a serverless TEMPLATE (the stock worker-comfyui
# image, our env, our start.sh off the volume as the start command) and
# an ENDPOINT on that template with the weights volume attached, pinned to the
# volume's data center, 0..1 workers, a short idle timeout. Re-running updates
# the template in place (a handler change needs `runpod-volume-setup.sh
# --code-only` too) and leaves an existing endpoint alone.
#
# Then it proves the endpoint answers: a `{"op": "ping"}` job, which lists
# what the worker sees on the volume without touching the GPU — and which is a
# COLD START, so it also says how long one takes and costs a few cents.
#
# Prerequisites: `runpod-volume-setup.sh` has run (the weights and the code are
# on the volume). The endpoint id it prints goes into the registry entry
# `wan-2.2-i2v-studio` as `runpod/<id>` in backend/studio_core/models.json and
# the e2e fixture.
#
# Usage:
#   ./studio/scripts/runpod-endpoint-up.sh
#   ./studio/scripts/runpod-endpoint-up.sh --image ghcr.io/you/studio-wan22:tag   # a built image; no start-command override
#   ./studio/scripts/runpod-endpoint-up.sh --no-ping
#
# Cost: idle is $0 — min workers 0, and a worker scales down `idle-timeout`
# seconds after its last job. Active is the GPU's per-second flex price for
# as long as a job runs (H100 $0.00116/s ≈ $4.18/h). The volume is the only
# standing cost (~$7/month at 100 GB).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=runpod-common.sh
source "$SCRIPT_DIR/runpod-common.sh"

IMAGE="$WAN22_IMAGE"
BAKED=0
PING=1
IDLE_TIMEOUT=60
EXECUTION_TIMEOUT_MS=$((40 * 60 * 1000))
while [[ $# -gt 0 ]]; do
  case "$1" in
    --image) IMAGE="$2"; BAKED=1; shift ;;
    --no-ping) PING=0 ;;
    --idle-timeout) IDLE_TIMEOUT="$2"; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

VOLUME_ID="$(runpod_volume_id)"
if [ -z "$VOLUME_ID" ]; then
  echo "no volume named $WAN22_VOLUME_NAME — run runpod-volume-setup.sh first" >&2
  exit 1
fi
echo "volume: $VOLUME_ID"

# The template. With the stock image, the start command is our start.sh off
# the volume, which copies the handler and the model paths into place and
# runs ComfyUI with our flags, then the handler. With a baked image the
# files are already there and the CMD is the image's (the same start.sh).
ENV_JSON="$(python3 -c '
import json, sys
print(json.dumps({
    "STUDIO_USD_PER_SECOND": sys.argv[1],
    "STUDIO_MAX_FRAMES": "241",
    "STUDIO_MAX_SECONDS": "2400",
    "COMFY_LOG_LEVEL": "INFO",
    "REFRESH_WORKER": "false",
}))' "$WAN22_USD_PER_SECOND")"
if [ "$BAKED" = 1 ]; then
  START_CMD='[]'
else
  START_CMD='["bash","/runpod-volume/studio/start.sh"]'
fi
TEMPLATE_BODY="$(python3 -c '
import json, sys
print(json.dumps({
    "name": sys.argv[1], "imageName": sys.argv[2], "isServerless": True,
    "containerDiskInGb": 30, "env": json.loads(sys.argv[3]),
    "dockerStartCmd": json.loads(sys.argv[4]), "ports": [],
    "readme": "studio Wan 2.2 I2V worker: studio/worker/wan22/ in andreas-services. Weights and handler on the network volume.",
}))' "$WAN22_TEMPLATE_NAME" "$IMAGE" "$ENV_JSON" "$START_CMD")"

TEMPLATE_ID="$(runpod_template_id)"
if [ -n "$TEMPLATE_ID" ]; then
  echo "updating template $TEMPLATE_ID"
  runpod_rest PATCH "/templates/$TEMPLATE_ID" "$TEMPLATE_BODY" >/dev/null
else
  TEMPLATE_ID="$(runpod_rest POST /templates "$TEMPLATE_BODY" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["id"])')"
  echo "created template $TEMPLATE_ID"
fi

ENDPOINT_ID="$(runpod_endpoint_id)"
if [ -n "$ENDPOINT_ID" ]; then
  echo "endpoint $WAN22_ENDPOINT_NAME exists: $ENDPOINT_ID (left as it is)"
else
  ENDPOINT_BODY="$(python3 -c '
import json, sys
print(json.dumps({
    "name": sys.argv[1], "templateId": sys.argv[2], "computeType": "GPU",
    "gpuTypeIds": json.loads(sys.argv[3]), "gpuCount": 1,
    "dataCenterIds": [sys.argv[4]], "networkVolumeId": sys.argv[5],
    "workersMin": 0, "workersMax": 1, "idleTimeout": int(sys.argv[6]),
    "executionTimeoutMs": int(sys.argv[7]), "flashboot": True,
    "scalerType": "QUEUE_DELAY", "scalerValue": 4,
}))' "$WAN22_ENDPOINT_NAME" "$TEMPLATE_ID" "$WAN22_GPU_TYPES" "$WAN22_DATA_CENTER" \
     "$VOLUME_ID" "$IDLE_TIMEOUT" "$EXECUTION_TIMEOUT_MS")"
  ENDPOINT_ID="$(runpod_rest POST /endpoints "$ENDPOINT_BODY" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("id") or d)')"
  echo "created endpoint $ENDPOINT_ID"
fi

echo
echo "endpoint id: $ENDPOINT_ID"
echo "registry model id: runpod/$ENDPOINT_ID"

if [ "$PING" = 1 ]; then
  echo
  echo "ping (a cold start: the image pull and ComfyUI's boot, no render)"
  STARTED=$(date +%s)
  JOB="$(curl -sS -X POST "https://api.runpod.ai/v2/$ENDPOINT_ID/run" \
    -H "Authorization: Bearer $(runpod_key)" -H 'Content-Type: application/json' \
    -d '{"input":{"op":"ping"}}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
  while :; do
    STATUS_JSON="$(curl -sS "https://api.runpod.ai/v2/$ENDPOINT_ID/status/$JOB" -H "Authorization: Bearer $(runpod_key)")"
    STATUS="$(printf '%s' "$STATUS_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
    case "$STATUS" in
      COMPLETED|FAILED|CANCELLED|TIMED_OUT) break ;;
    esac
    sleep 5
  done
  echo "$STATUS after $(( $(date +%s) - STARTED ))s"
  printf '%s\n' "$STATUS_JSON" | python3 -m json.tool
fi
