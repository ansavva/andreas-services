---
name: studio-media-hunyuan-video-lora-train
description: Train a character LoRA for Tencent's HunyuanVideo 13B as a recorded run of kind `training` — studio rents a Runpod GPU pod from a plain PyTorch image, installs musubi-tuner (ai-toolkit has no HunyuanVideo arch), trains on the character's images tagged `dataset` with their descriptions as captions, files every checkpoint under <character>/models/ and terminates the pod. Registered so the trainer exists; NOT YET USABLE END TO END — no hosted endpoint loads a HunyuanVideo LoRA into image-to-video, so nothing in studio can animate a still with what it trains, and the job has not run on a real pod. Read this page before renting anything.
---

# studio-media-hunyuan-video-lora-train

`runpod-pod/musubi-hunyuan-video` — the third trainer, and the one to know
the limits of before spending on it.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model hunyuan-video-lora-train …`,
> and `studio models show hunyuan-video-lora-train` for the knobs. The
> dataset, captions and trigger are exactly as
> [`studio-media-lora-train`](../studio-media-lora-train/SKILL.md) describes.

## Two things to know first

**1. Studio cannot use what it trains — yet.** Checked 2026-09-20:

| Where | What loads a custom HunyuanVideo LoRA |
|---|---|
| fal | nothing. `hunyuan-video-lora`, `hunyuan-video-img2vid-lora` and the training endpoint answer 404; `hunyuan-video-image-to-video` and `hunyuan-video-v1.5/image-to-video` take no `loras` |
| Replicate | `zsxkib/hunyuan-video-lora` (January 2025) — **text-to-video only**, a bare `lora_url` string. Not an image-to-video endpoint and not the `{path, scale}` shape studio's LoRA sends take |
| Runpod public endpoints | none for HunyuanVideo |

So a file this trainer leaves has no `--lora-key` destination in the
registry. The trainer is here so the job exists and the naming is settled;
the budget went to [`studio-media-ltx-2-3-lora-train`](../studio-media-ltx-2-3-lora-train/SKILL.md),
whose LoRA fal serves.

**2. The job has not run on a real pod.** It is written against
musubi-tuner's own HunyuanVideo guide and the fake pod covers what studio
does with it, not what the trainer does. The first real run is an
experiment, at pod prices; read the log tail in the run's response if it
fails.

## What differs from the other trainers

| | |
|---|---|
| The trainer | kohya-ss/musubi-tuner, installed on the pod at the start of the job (a plain PyTorch image; no ai-toolkit) |
| The model | the official 720p text-to-video transformer and VAE, ComfyUI's repackaged text encoders — none gated |
| The stages | latents cached, text-encoder outputs cached, then training — musubi's own order; the first two show in the log before a step is counted |
| The files | one per checkpoint, `<character>-<trigger>-<run>_<step>.safetensors` and the same without a step for the final one, converted on the pod to the diffusers/ComfyUI key layout before upload |
| Samples | **none** — `sample_prompts` must be `[]` (the entry's default); a prompt list is refused before anything rents |
| `lr` | default **2e-4**, musubi's documented starting point for this model (Wan's is 1e-4) |
| `gpu` | default **`h100`** |
| No `base` | one model, no mode to pick |

## Invoke

```bash
studio run --model hunyuan-video-lora-train --project <project> \
  --character <name> --pick-tag dataset \
  --extra '{"trigger":"ohwx_pt","steps":1500}' \
  --dry-run

studio runs submit <run>       # hard rule #2: this is the act
```
