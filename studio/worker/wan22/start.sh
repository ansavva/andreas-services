#!/usr/bin/env bash
# The worker's start: ComfyUI in the background, then the handler — the stock
# image's start.sh minus its SSH and API-serving branches, plus our ComfyUI
# flags. The endpoint template runs this off the network volume
# (`bash /runpod-volume/studio/start.sh`); the Dockerfile bakes it as CMD.
#
# COMFY_ARGS is the one knob, empty by default. `--disable-dynamic-vram` was
# tried on 2026-09-20 on the suspicion that ComfyUI 0.34's dynamic loading
# was streaming the expert every step (81 and 121 frames both took 34 s a
# step); it changed nothing — a step is 17-18 s a pass on an H100 at 720p
# either way — so the stock behaviour stays.
set -euo pipefail

STUDIO_DIR="${STUDIO_DIR-/runpod-volume/studio}"
COMFY_ROOT="${COMFY_ROOT:-/comfyui}"
: "${COMFY_LOG_LEVEL:=INFO}"
: "${COMFY_ARGS:=}"

# The stock image's handler is replaced by ours; its model paths by ours.
# A baked image already has both in place and sets STUDIO_DIR empty.
if [ -n "$STUDIO_DIR" ] && [ -f "$STUDIO_DIR/handler.py" ]; then
  cp "$STUDIO_DIR/handler.py" /handler.py
  cp "$STUDIO_DIR/extra_model_paths.yaml" "$COMFY_ROOT/extra_model_paths.yaml"
fi

TCMALLOC="$(ldconfig -p | grep -Po "libtcmalloc.so.\d" | head -n 1 || true)"
export LD_PRELOAD="${TCMALLOC}"

echo "studio-wan22: starting ComfyUI ($COMFY_ARGS)"
# shellcheck disable=SC2086
python -u "$COMFY_ROOT/main.py" --disable-auto-launch --disable-metadata \
  --listen 127.0.0.1 --port 8188 --verbose "$COMFY_LOG_LEVEL" --log-stdout $COMFY_ARGS &
echo $! > /tmp/comfyui.pid

echo "studio-wan22: starting the handler"
exec python -u /handler.py
