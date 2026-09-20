#!/usr/bin/env bash
# Runs ON a pod that has the network volume mounted (runpod-volume-setup.sh
# copies it there). Downloads the Wan 2.2 I2V A14B weights ComfyUI wants into
# the volume's models/ tree, laid out the way worker/wan22/extra_model_paths.yaml
# names them. Idempotent: a file already there is not fetched again.
#
#   diffusion_models/  wan2.2_i2v_high_noise_14B_fp16.safetensors   28.6 GB
#                      wan2.2_i2v_low_noise_14B_fp16.safetensors    28.6 GB
#   text_encoders/     umt5_xxl_fp8_e4m3fn_scaled.safetensors         6.7 GB
#   vae/               wan_2.1_vae.safetensors                        0.25 GB
#
# fp16 for the two experts and not fp8: the LoRA pair is what this endpoint
# exists for, and ComfyUI folds a LoRA into the weight dtype — into fp8 that
# rounds the adapter away. The 57 GB pair fits an 80 GB card with one expert
# resident at a time, which ComfyUI does on its own.
set -euo pipefail
ROOT=${1:-/workspace}
M=$ROOT/models
mkdir -p "$M/diffusion_models" "$M/vae" "$M/text_encoders" "$M/loras/studio-cache" "$ROOT/studio"

uv pip install -q "huggingface_hub[hf_transfer]" 2>&1 | tail -1 || true
export HF_HUB_ENABLE_HF_TRANSFER=1
R22=Comfy-Org/Wan_2.2_ComfyUI_Repackaged
R21=Comfy-Org/Wan_2.1_ComfyUI_repackaged

# fetch <repo> <path-in-repo> <destination-dir>
fetch() {
  local repo=$1 path=$2 dest=$3 name
  name=$(basename "$path")
  if [ -s "$dest/$name" ]; then
    echo "have $name"
    return
  fi
  hf download "$repo" "$path" --local-dir "$ROOT/hf-tmp"
  mv "$ROOT/hf-tmp/$path" "$dest/$name"
}

fetch "$R22" split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp16.safetensors "$M/diffusion_models" &
fetch "$R22" split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp16.safetensors "$M/diffusion_models" &
fetch "$R22" split_files/vae/wan_2.1_vae.safetensors "$M/vae" &
fetch "$R21" split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors "$M/text_encoders" &
wait

# The Lightning 4-step distillation pair behind the handler's `mode: fast`
# (lightx2v, Seko V1, rank 64, 1.2 GB each), renamed to what handler.py loads.
LIGHT=lightx2v/Wan2.2-Lightning
LDIR=Wan2.2-I2V-A14B-4steps-lora-rank64-Seko-V1
mkdir -p "$M/loras/lightning"
for stage in high low; do
  if [ ! -s "$M/loras/lightning/wan2.2_i2v_lightning_4step_$stage.safetensors" ]; then
    hf download "$LIGHT" "$LDIR/${stage}_noise_model.safetensors" --local-dir "$ROOT/hf-tmp"
    mv "$ROOT/hf-tmp/$LDIR/${stage}_noise_model.safetensors" "$M/loras/lightning/wan2.2_i2v_lightning_4step_$stage.safetensors"
  fi
done

rm -rf "$ROOT/hf-tmp"
ls -la "$M"/diffusion_models "$M"/text_encoders "$M"/vae "$M"/loras/lightning
du -sh "$M"
