#!/usr/bin/env bash
# PID 1 of a lora-lab pod. Replaces `pod bootstrap` outright: by the time SSH
# answers, ComfyUI is already starting against the volume and there is nothing
# left to install.
#
# ORDERING IS THE DEBUGGING STORY. RunPod exposes no API for boot logs — a
# container that dies before sshd is a restart loop only the console UI can
# see. So sshd starts FIRST, unconditionally, and everything after it is
# best-effort and logged to /workspace/entrypoint.log: a broken pod stays a
# reachable pod, and the diagnosis is one ssh away instead of console-only.
#
# Config arrives as env vars on the create-pod call (adapters/runpod.py):
#   PUBLIC_KEY  what sshd trusts — RunPod's own convention, kept
#   HF_TOKEN    for gated HuggingFace downloads onto the volume
#
# The privacy line, drawn in paths:
#   /weights    the network volume — public model weights and tools ONLY.
#               Survives Terminate on purpose; nothing subject-derived may
#               land here. `lora-lab pod verify` audits it.
#   /workspace  container disk — dataset, training output, checkpoints,
#               renders. Destroyed by Terminate, which is the point.
set -u

# ---------------------------------------------------------------- sshd first
mkdir -p /workspace /root/.ssh && chmod 700 /root/.ssh
if [ -n "${PUBLIC_KEY:-}" ]; then
  echo "$PUBLIC_KEY" > /root/.ssh/authorized_keys
  chmod 600 /root/.ssh/authorized_keys
fi
ssh-keygen -A                     # fresh host keys per pod; the CLI uses accept-new
mkdir -p /run/sshd
/usr/sbin/sshd || echo "sshd failed to start" >> /workspace/entrypoint.log

# Everything below is best-effort, and says what it did.
exec >> /workspace/entrypoint.log 2>&1
echo "=== entrypoint $(date -u +%FT%TZ) ==="

# ---------------------------------------------------------------- filesystem
mkdir -p /workspace/dataset /workspace/train /workspace/comfy-out
# On a pod created without the volume these become plain container dirs —
# everything still works, it just re-downloads. `pod verify` calls that out.
mkdir -p /weights/models /weights/tools /weights/hf-cache

# Back-compat breadcrumbs: the CLI's fallback paths read these two files, and
# in this image their answers are fixed.
echo /opt/ComfyUI > /workspace/.comfydir
echo python3.12   > /workspace/.pybin

# ---------------------------------------------------------------- env handoff
# SSH sessions do not inherit PID 1's environment, so persist what pod-side
# scripts need. A 0600 root-only file on a single-tenant pod — same posture as
# the old push_token, minus the scp round trip. Never on a command line.
{
  printf 'HF_TOKEN=%s\n' "${HF_TOKEN:-}"
  printf 'HF_HOME=%s\n'  "${HF_HOME:-/weights/hf-cache}"
} > /etc/lab.env
chmod 600 /etc/lab.env

# ---------------------------------------------------------------- ComfyUI
# 127.0.0.1 only — the SSH tunnel is the single way in, unchanged. Models
# resolve through extra-paths.yaml onto /weights; outputs (subject renders)
# are forced onto the container disk. loras is deliberately NOT mapped to the
# volume: trained checkpoints are subject-derived and must die with the pod.
tmux new-session -d -s comfy \
  "cd /opt/ComfyUI && python3.12 main.py --listen 127.0.0.1 --port 8188 \
     --extra-model-paths-config /opt/lab/pod-scripts/extra-paths.yaml \
     --output-directory /workspace/comfy-out \
     2>&1 | tee -a /workspace/comfy.log" \
  && echo "comfy tmux started" || echo "comfy tmux FAILED"

echo "entrypoint done"
exec sleep infinity
