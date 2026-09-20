#!/usr/bin/env bash
# Shared by runpod-volume-setup.sh, runpod-endpoint-up.sh and runpod-endpoint-down.sh:
# the Runpod key, a REST helper, and the names the three scripts agree on.
#
# The key is RUNPOD_API_KEY if exported, else the one in
# ~/.config/andreas-services/studio/prod.env — the same key the deployed API
# spends under, because the endpoint these scripts manage is the one that API
# calls. It is never printed.
#
# Everything here is `rest.runpod.io/v1` over curl rather than runpodctl,
# because endpoint creation needs a LIST of GPU types (`gpuTypeIds`) and a
# template needs a `dockerStartCmd` array, and the CLI takes one `--gpu-id`.

RUNPOD_CONFIG_DIR="${RUNPOD_CONFIG_DIR:-$HOME/.config/andreas-services/studio}"

#: Names. Changing one here changes it everywhere the scripts look things up.
WAN22_VOLUME_NAME="studio-prod-wan22-weights"
WAN22_ENDPOINT_NAME="studio-prod-wan22"
WAN22_TEMPLATE_NAME="studio-prod-wan22"
#: The stock image the worker runs on; the Dockerfile in worker/wan22/ is FROM it.
WAN22_IMAGE="${WAN22_IMAGE:-runpod/worker-comfyui:5.10.0-base}"
#: One data center: a network volume lives in exactly one, and the endpoint's
#: workers have to be there too. US-CA-2 had H100 SXM, A100 SXM and H100 NVL
#: when the volume was made (2026-09-20); the volume cannot move.
WAN22_DATA_CENTER="${WAN22_DATA_CENTER:-US-CA-2}"
#: In priority order. 80 GB is the floor: the fp16 pair is 2 x 28.6 GB and
#: ComfyUI keeps one expert resident while the other samples.
WAN22_GPU_TYPES='["NVIDIA H100 80GB HBM3","NVIDIA A100-SXM4-80GB","NVIDIA A100 80GB PCIe","NVIDIA H100 NVL","NVIDIA H100 PCIe"]'
#: Dollars per worker-second the handler reports as `cost`. Runpod's flex
#: price for the first GPU in the list (H100, September 2026).
WAN22_USD_PER_SECOND="${WAN22_USD_PER_SECOND:-0.00116}"

runpod_key() {
  if [ -n "${RUNPOD_API_KEY:-}" ]; then
    printf '%s' "$RUNPOD_API_KEY"
    return
  fi
  local file="$RUNPOD_CONFIG_DIR/prod.env"
  if [ ! -f "$file" ]; then
    echo "no RUNPOD_API_KEY in the environment and no $file" >&2
    exit 1
  fi
  grep '^RUNPOD_API_KEY=' "$file" | cut -d= -f2- | tr -d '"'"'"
}

# runpod_rest <method> <path> [json-body]
runpod_rest() {
  local method=$1 path=$2 body=${3:-}
  if [ -n "$body" ]; then
    curl -sS -X "$method" "https://rest.runpod.io/v1$path" \
      -H "Authorization: Bearer $(runpod_key)" -H 'Content-Type: application/json' -d "$body"
  else
    curl -sS -X "$method" "https://rest.runpod.io/v1$path" \
      -H "Authorization: Bearer $(runpod_key)"
  fi
}

# runpod_graphql <query>
runpod_graphql() {
  curl -sS -X POST https://api.runpod.io/graphql \
    -H "Authorization: Bearer $(runpod_key)" -H 'Content-Type: application/json' \
    -d "$(python3 -c 'import json,sys; print(json.dumps({"query": sys.argv[1]}))' "$1")"
}

runpod_balance() {
  runpod_graphql '{ myself { clientBalance } }' | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["myself"]["clientBalance"])'
}

# The id of the named volume / endpoint / template, or nothing.
runpod_volume_id() {
  runpod_rest GET /networkvolumes | python3 -c '
import json, sys
for v in json.load(sys.stdin) or []:
    if v.get("name") == sys.argv[1]:
        print(v["id"]); break' "$WAN22_VOLUME_NAME"
}
runpod_endpoint_id() {
  runpod_rest GET /endpoints | python3 -c '
import json, sys
for e in json.load(sys.stdin) or []:
    if e.get("name") == sys.argv[1]:
        print(e["id"]); break' "$WAN22_ENDPOINT_NAME"
}
runpod_template_id() {
  runpod_rest GET /templates | python3 -c '
import json, sys
for t in json.load(sys.stdin) or []:
    if t.get("name") == sys.argv[1]:
        print(t["id"]); break' "$WAN22_TEMPLATE_NAME"
}

runpod_ctl() {
  RUNPOD_API_KEY="$(runpod_key)" runpodctl "$@"
}
