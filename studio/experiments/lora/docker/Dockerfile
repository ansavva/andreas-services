# syntax=docker/dockerfile:1
# The lora-lab pod image: everything `pod bootstrap` used to assemble over SSH,
# decided once at build time on a machine we control instead of at runtime over
# whatever link the rented pod happened to draw.
#
# The split (mirrors the RunPod deployment pattern):
#   image  = code + deps   — this file. ComfyUI pinned, PuLID nodes, tooling.
#   volume = weights       — /weights, a persistent network volume. Nothing here.
#   env    = config        — PUBLIC_KEY, HF_TOKEN, injected at pod creation.
#
# NOTHING subject-related may enter this image: no photos, no tokens, no
# character data, no checkpoints. It is generic software only — the same hard
# rule #1 posture as the rest of the lab, applied to a registry.
#
# Base: the torch triple measured working on 2026-08-24 (RUNBOOK "Lazy
# install"). Known quirk of this base, also measured: torch lives under
# python3.12 while `python3` is 3.10 — so every install and every run below
# names python3.12 explicitly. The entrypoint records it in /workspace/.pybin
# for the CLI.
FROM runpod/pytorch:1.1.0-cu1290-torch291-ubuntu2204

# Pinned by build.sh to a concrete commit, because the workflow graphs in
# assets/workflows/ are wired to specific node signatures — a ComfyUI that
# silently moves forward can break a graph that worked yesterday. Same
# reasoning as the old DEFAULT_IMAGE pin in adapters/runpod.py.
ARG COMFY_REF
RUN test -n "$COMFY_REF" || (echo "COMFY_REF build-arg is required — use build.sh" && false)

ENV DEBIAN_FRONTEND=noninteractive \
    PYBIN=python3.12 \
    HF_HOME=/weights/hf-cache

# Freeze the base's torch triple and pin EVERY pip call in this build to it.
# Both attempts to bake this image replaced torch otherwise: the ComfyUI
# requirements layer (not PuLID, as first assumed — the build log shows the
# uninstall there) resolves some transitive dep into torch 2.13+cu130, which
# demands a CUDA 13 driver and gets the image refused by RunPod's 12.8/12.9
# hosts. PIP_CONSTRAINT is env-wide so no later layer can repeat the mistake;
# ssh sessions on the pod do not inherit image ENV, so OneTrainer's venv on
# the volume keeps its own pins.
RUN python3.12 -m pip freeze | grep -E '^(torch|torchvision|torchaudio)==' > /opt/torch-constraints.txt && \
    cat /opt/torch-constraints.txt
ENV PIP_CONSTRAINT=/opt/torch-constraints.txt

# build-essential + cmake are for insightface, which compiles a cython
# extension at install time. Everything else is the old bootstrap's apt list
# plus openssh-server (our entrypoint runs sshd itself rather than depending
# on the base image's start script).
RUN apt-get update -qq && \
    apt-get install -y -qq git aria2 tmux libgl1 libglib2.0-0 rsync \
        openssh-server build-essential cmake && \
    rm -rf /var/lib/apt/lists/*

# ComfyUI at a fixed, image-owned path. /opt, not /workspace: /workspace is
# the pod's container disk (subject data, destroyed at Terminate), and nothing
# durable may depend on it. Requirements install with torch grepped out — the
# bare `torch` line invites the resolver to replace the image's CUDA build,
# and did, on 2026-08-24 (see the old pod-bootstrap.sh).
RUN git clone https://github.com/comfyanonymous/ComfyUI /opt/ComfyUI && \
    cd /opt/ComfyUI && git checkout "$COMFY_REF" && \
    grep -vE '^(torch|torchvision|torchaudio)([[:space:]]|==|>=|$)' requirements.txt \
      > /tmp/requirements-no-torch.txt && \
    python3.12 -m pip install --no-cache-dir -r /tmp/requirements-no-torch.txt

# PuLID's custom nodes and their pip stack — the heaviest per-pod install the
# lab had (~3GB of insightface/onnxruntime), now a build-time layer. The node
# pack loads at every ComfyUI start, so the old "installing pulid restarts
# ComfyUI" wrinkle is gone with it. Weights still arrive via pod-assets.sh
# onto the volume; only code lives here.
#
# The constraints file is load-bearing: without it, facexlib's bare `torch`
# dependency let pip upgrade the base's 2.9.1+cu129 to 2.13.0+cu130 — an
# image that then demanded a CUDA 13 driver and was refused by the 12.8/12.9
# hosts RunPod actually rents ("Current machine CUDA version is 12.8, but the
# required version for this image is 12.9", measured 2026-08-25). Freezing
# the base's own torch triple makes the resolver keep it, whatever any
# dependency asks for.
RUN git clone --depth 1 https://github.com/sipie800/ComfyUI-PuLID-Flux-Enhanced \
      /opt/ComfyUI/custom_nodes/ComfyUI-PuLID-Flux-Enhanced && \
    python3.12 -m pip install --no-cache-dir \
      -r /opt/ComfyUI/custom_nodes/ComfyUI-PuLID-Flux-Enhanced/requirements.txt && \
    python3.12 -m pip install --no-cache-dir insightface onnxruntime-gpu facexlib ftfy timm

# Refuse to ship an image whose torch got replaced or whose ComfyUI cannot
# import — the build-time version of the old bootstrap's final check.
RUN python3.12 - <<'PY'
import sys, torch
parts = torch.__version__.split("+")[0].split(".")
if (int(parts[0]), int(parts[1])) < (2, 7):
    sys.exit(f"torch is {torch.__version__} — the requirements install replaced it")
if torch.version.cuda != "12.9":
    # The base ships cu129 and the rentable hosts speak 12.8/12.9/13.0. A
    # different CUDA build here means a dependency beat the constraints file
    # and most hosts will refuse the image — fail the build instead.
    sys.exit(f"torch CUDA build is {torch.version.cuda}, expected 12.9 — "
             "a dependency replaced the base torch")
sys.path.insert(0, "/opt/ComfyUI")
print("torch", torch.__version__, "cuda", torch.version.cuda)
PY

# The lab's pod-side material, staged by build.sh from assets/ so the build
# context can never include local/ (subject data).
COPY lab/ /opt/lab/
RUN chmod +x /opt/lab/entrypoint.sh /opt/lab/pod-assets.sh

CMD ["/opt/lab/entrypoint.sh"]
