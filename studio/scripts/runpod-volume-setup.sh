#!/usr/bin/env bash
# Put the Wan 2.2 weights — and the worker's code — on the endpoint's network volume.
#
# One-shot, and idempotent: creates the volume if it is missing, rents a pod
# with the volume at /workspace, downloads the four weight files ComfyUI wants
# (about 64 GB; a couple of minutes from Hugging Face on a Runpod link), copies
# `worker/wan22/handler.py` and `extra_model_paths.yaml` to `/workspace/studio/`,
# and terminates the pod. A serverless worker sees the same volume at
# `/runpod-volume`, which is the path the yaml and the handler use.
#
# Why the code rides on the volume: the endpoint runs the STOCK
# `runpod/worker-comfyui` image, and its template's start command is our
# start.sh off the volume, which puts the handler in place and starts ComfyUI. That is what
# lets a handler change ship without a registry, an image build or a Docker
# daemon. `worker/wan22/Dockerfile` is the same two files baked in, for a
# machine that has all three.
#
# Usage:
#   ./studio/scripts/runpod-volume-setup.sh              # weights + code
#   ./studio/scripts/runpod-volume-setup.sh --code-only  # just the two files (a handler edit)
#
# Cost: the pod, for as long as the download takes (an A40/A5000 is ~$0.3/h;
# `--gpu-id` picks another), plus the volume: 100 GB at $0.07/GB/month ≈ $7/month,
# the endpoint's only standing cost. Nothing here touches the endpoint.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=runpod-common.sh
source "$SCRIPT_DIR/runpod-common.sh"
WORKER_DIR="$SCRIPT_DIR/../worker/wan22"

CODE_ONLY=0
GPU_ID="${WAN22_SETUP_GPU:-NVIDIA A40}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --code-only) CODE_ONLY=1 ;;
    --gpu-id) GPU_ID="$2"; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

echo "balance before: \$$(runpod_balance)"

VOLUME_ID="$(runpod_volume_id)"
if [ -z "$VOLUME_ID" ]; then
  echo "creating volume $WAN22_VOLUME_NAME (100 GB, $WAN22_DATA_CENTER)"
  VOLUME_ID="$(runpod_rest POST /networkvolumes \
    "{\"name\":\"$WAN22_VOLUME_NAME\",\"size\":100,\"dataCenterId\":\"$WAN22_DATA_CENTER\"}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
fi
echo "volume: $VOLUME_ID"

# A pod on the stock image, sshd and nothing else: the image's start.sh would
# start ComfyUI and a job loop this pod has no use for.
START='mkdir -p ~/.ssh && echo "$PUBLIC_KEY" > ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys && ssh-keygen -A && service ssh start && sleep infinity'
TERMINATE_AFTER="$(python3 -c 'import datetime as d; print((d.datetime.now(d.timezone.utc)+d.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"))')"
echo "renting a $GPU_ID pod in $WAN22_DATA_CENTER (auto-terminates $TERMINATE_AFTER)"
POD_JSON="$(runpod_ctl pod create --name studio-wan22-setup \
  --image "$WAN22_IMAGE" --gpu-id "$GPU_ID" --data-center-ids "$WAN22_DATA_CENTER" \
  --network-volume-id "$VOLUME_ID" --volume-mount-path /workspace \
  --container-disk-in-gb 20 --ssh --ports 22/tcp \
  --docker-args "bash -c '$START'" \
  --terminate-after "$TERMINATE_AFTER" --wait --wait-timeout 15m)"
POD_ID="$(printf '%s' "$POD_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
trap 'echo "removing pod $POD_ID"; runpod_ctl pod remove "$POD_ID" >/dev/null || true' EXIT

read -r POD_IP POD_PORT KEY_PATH < <(runpod_ctl ssh info "$POD_ID" | python3 -c '
import json, sys
d = json.load(sys.stdin); print(d["ip"], d["port"], d["ssh_key"]["path"])')
SSH=(ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -p "$POD_PORT" "root@$POD_IP")
SCP=(scp -i "$KEY_PATH" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -P "$POD_PORT")

# sshd is reachable before the start command has written authorized_keys;
# retry the first command rather than fail on the race.
for _ in $(seq 1 20); do
  if "${SSH[@]}" 'mkdir -p /workspace/studio' 2>/dev/null; then break; fi
  sleep 5
done

echo "copying the worker's code to the volume"
"${SCP[@]}" "$WORKER_DIR/handler.py" "$WORKER_DIR/extra_model_paths.yaml" "$WORKER_DIR/start.sh" "root@$POD_IP:/workspace/studio/"

if [ "$CODE_ONLY" = 0 ]; then
  echo "downloading the weights (this is the part that takes minutes)"
  "${SCP[@]}" "$WORKER_DIR/download-weights.sh" "root@$POD_IP:/root/"
  "${SSH[@]}" 'export PATH=/opt/venv/bin:$PATH; bash /root/download-weights.sh /workspace'
fi

"${SSH[@]}" 'ls -la /workspace/studio; du -sh /workspace/models 2>/dev/null || true'
echo "volume $VOLUME_ID is ready; balance after: \$$(runpod_balance)"
