#!/usr/bin/env bash
# Weights and tools, fetched one component at a time — onto /weights, the
# persistent network volume, so each is paid for ONCE EVER rather than once
# per pod:
#
#   encoders    clip_l + t5xxl        shared by flux1dev, sd35 and ltx098
#   flux1dev    FLUX.1-dev fp8        image; needs `encoders`; VAE is GATED
#   flux2dev    FLUX.2-dev fp8mixed   image; ungated via the Comfy-Org repack
#   sd35        SD 3.5 Large fp8      image; needs `encoders` + clip_g
#   ltx098      LTX-Video 13B 0.9.8   video; needs `encoders` (reuses t5xxl)
#   ltx23       LTX-2.3 22B fp8       video; ungated
#   ltx25       LTX-2.5 22B int8      video; GATED
#   wan         Wan 2.2 TI2V 5B       video
#   wan14b      Wan 2.2 T2V 14B pair  video
#   pulid       PuLID face-stack weights   only `expand`/`masks` need these
#   onetrainer  OneTrainer + FLUX base     only `train` needs this; ~32GB
#
# This script ships INSIDE the pod image at /opt/lab/pod-assets.sh — nothing
# scps it anymore. The PuLID custom nodes and their pip stack, which used to
# install here (~3GB per pod, plus a ComfyUI restart), are baked into the
# image; only their weights remain.
#
# THE PRIVACY LINE: everything this script writes lands on /weights, which
# survives Terminate. That is safe precisely because everything here is a
# public download — a model anyone can fetch from HuggingFace or GitHub.
# Nothing subject-derived may ever be added to this file. Subject data lives
# under /workspace (container disk) and dies with the pod.
#
# Each component drops /weights/.asset-<name>-done so the CLI can tell what is
# present without listing the volume — and, being on the volume, "present"
# now survives pods. Every step is idempotent: a dropped connection is a
# re-run, not a rebuild.
set -euo pipefail

: "${HF_TOKEN:?HF_TOKEN is required}"

COMPONENT="${1:?usage: pod-assets.sh <component>}"
# Fixed by the image — no discovery. /opt/ComfyUI holds the code; every model
# class the engines share resolves through extra-paths.yaml onto /weights.
M=/weights/models
T=/weights/tools
PYBIN=python3.12

log() { printf '\n=== %s ===\n' "$*"; }

hf() { # hf <repo> <remote-path> <dest-dir> [dest-name]
  local repo="$1" remote="$2" dir="$3" name="${4:-$(basename "$2")}"
  if [ -s "$dir/$name" ]; then echo "have $name"; return; fi
  mkdir -p "$dir"
  aria2c -x8 -s8 --console-log-level=warn --summary-interval=30 \
    --header="Authorization: Bearer $HF_TOKEN" \
    -d "$dir" -o "$name" \
    "https://huggingface.co/$repo/resolve/main/$remote"
}

WAN=Comfy-Org/Wan_2.2_ComfyUI_Repackaged
SD35=Comfy-Org/stable-diffusion-3.5-fp8

case "$COMPONENT" in
  encoders)
    # One T5-XXL and one CLIP-L serve FLUX, SD 3.5 and LTX 0.9.8 alike, so
    # they are their own component rather than a line in three others.
    log "shared text encoders (CLIP-L, T5-XXL fp8)"
    hf comfyanonymous/flux_text_encoders clip_l.safetensors $M/clip
    hf comfyanonymous/flux_text_encoders t5xxl_fp8_e4m3fn.safetensors $M/clip
    touch /weights/.asset-encoders-done
    ;;
  flux1dev)
    log "FLUX.1-dev fp8 UNet (Kijai mirror, ungated)"
    hf Kijai/flux-fp8 flux1-dev-fp8.safetensors $M/unet
    # The VAE is the gated part, not the UNet: it comes from the BFL repo and
    # 403s unless the account behind HF_TOKEN accepted FLUX.1-dev's licence.
    log "FLUX VAE (GATED — needs the accepted licence)"
    hf black-forest-labs/FLUX.1-dev ae.safetensors $M/vae
    touch /weights/.asset-flux1dev-done
    ;;
  flux2dev)
    # FLUX.2-dev through Comfy-Org's repack, which is ungated where
    # black-forest-labs/FLUX.2-dev is gated=auto. The licence is unchanged and
    # still non-commercial — only the download gate differs. FLUX.2-klein-4B
    # is the Apache-2.0 one, if that matters for the output.
    #
    # 35.5GB against 24GB of VRAM, plus an 18GB text encoder: this does not fit
    # on the card. It is the LTX-2.3 bet — stream it from the pod's 503GB of
    # system RAM — and unverified as of 2026-08-24.
    #
    # Its own text encoder is a Mistral 3 Small, not the shared T5-XXL, and its
    # own VAE. So `encoders` buys nothing here and is not a dependency.
    log "FLUX.2-dev (fp8mixed) + Mistral-3-Small text encoder + VAE"
    F=Comfy-Org/flux2-dev
    hf $F split_files/diffusion_models/flux2_dev_fp8mixed.safetensors $M/diffusion_models
    hf $F split_files/text_encoders/mistral_3_small_flux2_fp8.safetensors $M/text_encoders
    hf $F split_files/vae/flux2-vae.safetensors $M/vae
    touch /weights/.asset-flux2dev-done
    ;;
  sd35)
    # SD 3.5 Large at fp8 from the Comfy-Org repack — ungated, where
    # stabilityai/stable-diffusion-3.5-large is gated=auto. Three text
    # encoders: CLIP-L and T5-XXL come from `encoders`, only CLIP-G is extra.
    log "Stable Diffusion 3.5 Large (fp8) + CLIP-G"
    hf $SD35 sd3.5_large_fp8_scaled.safetensors $M/checkpoints
    hf $SD35 text_encoders/clip_g.safetensors $M/clip
    touch /weights/.asset-sd35-done
    ;;
  ltx098)
    # The first LTX this lab smoked, kept only so the 2026-08-24 measurement in
    # RUNBOOK.md stays reproducible. Two generations old — do not start here.
    log "LTX-Video 13B 0.9.8 dev (fp8)"
    hf Lightricks/LTX-Video ltxv-13b-0.9.8-dev-fp8.safetensors $M/checkpoints
    touch /weights/.asset-ltx098-done
    ;;
  ltx23)
    # Ungated, and the only LTX-2.x with a local ComfyUI workflow template to
    # derive wiring from. 29.5GB against 24GB of VRAM: this does not fit on the
    # card and is not meant to — ComfyUI streams it from the pod's 503GB of
    # system RAM, and the distilled 8-step schedule keeps that affordable.
    log "LTX-2.3 22B distilled (fp8) + Gemma-3 12B text encoder"
    hf Lightricks/LTX-2.3-fp8 ltx-2.3-22b-distilled-fp8.safetensors $M/checkpoints
    hf Comfy-Org/ltx-2 split_files/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors \
       $M/text_encoders
    touch /weights/.asset-ltx23-done
    ;;
  ltx25)
    # GATED: huggingface.co/Lightricks/LTX-2.5 must have its licence accepted
    # by the account behind HF_TOKEN, or every file 403s with no other symptom.
    # Ships split rather than as one checkpoint, which is why stock loaders
    # cover it — see assets/workflows/smoke-ltx25.json.
    log "LTX-2.5 22B distilled (int8) + Gemma-4 text encoder"
    L=Lightricks/LTX-2.5
    hf $L diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors \
       $M/diffusion_models
    hf $L text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors \
       $M/text_encoders
    hf $L vae/ltx-2.5-video-vae-bf16.safetensors $M/vae
    # LTX-2.x is an audio+video model: the latents concat before the sampler
    # and separate after it, so the audio VAE is needed even for a silent
    # clip. 2.3 carries it inside its checkpoint; 2.5 ships it loose.
    hf $L vae/ltx-2.5-audio-vae-bf16.safetensors $M/vae
    hf $L model_patches/ltx-2.5-duration-head-bf16.safetensors $M/model_patches
    touch /weights/.asset-ltx25-done
    ;;
  wan)
    # The 5B TI2V: one file, text- and image-to-video, the variant Wan ships
    # for 24GB consumer cards. Note the VAE — 5B uses the higher-compression
    # wan2.2_vae, the 14B pair below uses the Wan 2.1 one. Not interchangeable.
    log "Wan 2.2 TI2V 5B"
    hf $WAN split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors $M/unet
    hf $WAN split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors $M/clip
    hf $WAN split_files/vae/wan2.2_vae.safetensors $M/vae
    touch /weights/.asset-wan-done
    ;;
  wan14b)
    # Wan 2.2's quality tier: a mixture-of-experts pair sampled in two stages,
    # high-noise then low-noise, which is why it is two 14.3GB files rather
    # than one. Takes the Wan 2.1 VAE, not the 5B's.
    log "Wan 2.2 T2V 14B (high + low noise, fp8)"
    hf $WAN split_files/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors $M/unet
    hf $WAN split_files/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors $M/unet
    hf $WAN split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors $M/clip
    hf $WAN split_files/vae/wan_2.1_vae.safetensors $M/vae
    touch /weights/.asset-wan14b-done
    ;;
  pulid)
    # Weights only — the custom nodes and their pip stack (insightface,
    # onnxruntime-gpu) are baked into the image, which also retired the
    # ComfyUI restart this component used to force.
    log "PuLID-FLUX weights"
    hf guozinan/PuLID pulid_flux_v0.9.1.safetensors $M/pulid
    log "EVA-CLIP (PuLID's image encoder)"
    hf QuanSun/EVA-CLIP EVA02_CLIP_L_336_psz14_s6B.pt $M/clip
    log "InsightFace antelopev2"
    ANTELOPE=$M/insightface/models/antelopev2
    if [ ! -s "$ANTELOPE/glintr100.onnx" ]; then
      mkdir -p "$ANTELOPE"
      aria2c -x8 -s8 --console-log-level=warn -d /tmp -o antelopev2.zip \
        "https://github.com/deepinsight/insightface/releases/download/v0.7/antelopev2.zip"
      python3 -c "import zipfile;zipfile.ZipFile('/tmp/antelopev2.zip').extractall('$M/insightface/models')"
    fi
    touch /weights/.asset-pulid-done
    ;;
  flux2base)
    # FLUX.2-dev TRAINING base — full diffusers snapshot (~115GB), OneTrainer
    # only; ComfyUI inference uses the separate fp8 `flux2dev` component.
    # GATED: HF account must have accepted the licence or every file 403s.
    OT=$T/OneTrainer
    [ -d $OT ] || { echo "onetrainer component must be installed first" >&2; exit 2; }
    log "FLUX.2-dev base for training (gated; ~115GB — minutes at DC speed)"
    HF_TOKEN=$HF_TOKEN $OT/venv/bin/python - <<'PY2'
from huggingface_hub import snapshot_download
import os
snapshot_download(
    "black-forest-labs/FLUX.2-dev",
    token=os.environ["HF_TOKEN"],
    local_dir="/weights/models/FLUX.2-dev",
    allow_patterns=["*.json", "*.txt", "*.model",
                    "text_encoder*/*", "tokenizer*/*", "vae/*", "transformer/*",
                    "scheduler*/*"],
)
print("FLUX.2 base present")
PY2
    touch /weights/.asset-flux2base-done
    ;;
  onetrainer)
    # The big one: OneTrainer's own venv plus a ~32GB FLUX.1-dev snapshot in
    # diffusers layout — once ever, now that both live on the volume. The venv
    # is built by the image's python3.12; if a future image tag moves the
    # python minor version, this venv's shebangs break and the fix is to
    # delete /weights/tools/OneTrainer and re-run.
    OT=$T/OneTrainer
    log "OneTrainer (own venv — its torch pins are its own business)"
    if [ ! -d $OT ]; then
      git clone --depth 1 https://github.com/Nerogar/OneTrainer $OT
      $PYBIN -m venv $OT/venv
      $OT/venv/bin/pip install -q --upgrade pip
      $OT/venv/bin/pip install -q -r $OT/requirements.txt
    fi
    log "FLUX.1-dev base for training (gated; big)"
    $OT/venv/bin/pip show -q huggingface_hub || $OT/venv/bin/pip install -q huggingface_hub
    HF_TOKEN=$HF_TOKEN $OT/venv/bin/python - <<'PY'
from huggingface_hub import snapshot_download
import os
snapshot_download(
    "black-forest-labs/FLUX.1-dev",
    token=os.environ["HF_TOKEN"],
    local_dir="/weights/models/FLUX.1-dev",
    allow_patterns=["*.json", "*.txt", "*.model",
                    "text_encoder*/*", "tokenizer*/*", "vae/*", "transformer/*",
                    "scheduler/*"],
)
print("base model present")
PY
    touch /weights/.asset-onetrainer-done
    ;;
  *)
    echo "unknown component: $COMPONENT" >&2
    exit 2
    ;;
esac

log "$COMPONENT ready"
