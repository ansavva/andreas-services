---
name: studio-media-wan-2-2-i2v-lora
description: Animate one still into video with Alibaba's Wan 2.2 at 720p WHILE LOADING YOUR OWN LoRA (runpod/wan-2-2-t2v-720-lora) on Runpod's public endpoint, as a recorded run — the one model in the harness that takes weights that are not its own. Use when a clip must carry a trained character LoRA, a camera-move LoRA, or any Wan 2.2 adapter pair, and as the baseline the character-LoRA work is scored on. A LoRA is a .safetensors node in the library bound with --lora-high-key / --lora-low-key, never a pasted URL. 5 or 8 seconds, per clip. For Wan without a LoRA use studio-media-wan-2-6-i2v.
---

# studio-media-wan-2-2-i2v-lora

`runpod/wan-2-2-t2v-720-lora` — Wan 2.2 image-to-video at 720p, served by
**Runpod's public endpoint**, with one thing no other engine here has: it
loads **LoRA weights you hand it**. Wan 2.2 samples in two stages — a
high-noise expert that decides composition and motion, then a low-noise one
that decides detail — and each takes its own adapter, which is why the
endpoint has two lists and a trained Wan 2.2 LoRA ships as a pair.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model wan-2.2-i2v-lora …`,
> and `studio models show wan-2.2-i2v-lora` for the schema. This page covers
> only what is specific to this model.

## What is specific to this model

| | |
|---|---|
| Provider | **Runpod**, not Replicate. The endpoint's id is `wan-2-2-t2v-720-lora` although it takes an image; Runpod's own docs table links a name that does not exist |
| Schema | Runpod publishes none, so the registry entry **is** the schema |
| Images field | **one start frame, required**: `image`, bound with `--start-run` / `--start-key`. No reference list, no end frame |
| **LoRAs** | `high_noise_loras` and `low_noise_loras`, each a list of `{path, scale}`. **A LoRA is a send**: a `.safetensors` node in the library, bound with `--lora-high-key` / `--lora-low-key` (repeatable), presigned at submit — the same rule every image follows (hard rule #3). A URL in the payload is refused |
| LoRA scale | `lora_scale` 0–2 (default 1) — **studio's one number**, written into every adapter's `scale`; the endpoint never sees the name |
| Accepts | stills `.jpg .jpeg .png .webp`; weights `.safetensors` |
| Duration | `duration` — `5` (default) or `8` seconds |
| Size | none — 720p landscape, always. `--aspect-ratio` does not apply |
| Seed | `seed` — `-1` (default) is random; any other integer repeats the draw |
| Safety checker | `enable_safety_checker` — on by default |
| Price | **per clip** (Runpod, September 2026): **$0.35 for 5 s, $0.56 for 8 s**. The run records what it charged |
| Not here | no reference images, no negative prompt, no size field, no step count. Wan 2.2's other knobs (`num_inference_steps`, `guidance`, `flow_shift`) are on the plain `wan-2-2-i2v-720` endpoint, which is not registered |

## Getting a LoRA into the library

A LoRA is a file like any other. Upload the pair once, into the folder of
whatever it belongs to — a character's `models/` for an identity LoRA, a
project's `input/` for a camera move being tried out:

```bash
studio upload --folder <project>/input ./orbit_high.safetensors ./orbit_low.safetensors
```

## Invoke

```bash
# the frame from the last image run, a public camera-move LoRA pair at 0.8
studio run --model wan-2.2-i2v-lora --project <project> \
  --start-run <project>/latest#1 \
  --lora-high-key <project>/input/orbit_high.safetensors \
  --lora-low-key  <project>/input/orbit_low.safetensors \
  --extra '{"duration":5,"seed":7,"lora_scale":0.8}' \
  --prompt "orbit 180 degrees around the subject"
```

Both flags repeat: two adapters on one stage go out as two objects with the
same `lora_scale`. Binding only one stage is allowed and is usually a
mistake — a Wan 2.2 pair is trained together.

## Prompting

Describe the motion, not the frame, and **say the trigger word the LoRA was
trained on** — for a camera-move adapter that is its verb (`orbit`), for a
character adapter it is the token its captions carried. A LoRA with no
trigger in the prompt is loaded and barely used.

## What it is for, and what it is not

**For:** the destination of a trained character LoRA — the same frame,
prompt and seed run with the adapter and without it is the comparison the
whole LoRA experiment is scored on; and public Wan 2.2 adapters (camera
moves, styles) over any still.

**Not a reference-image engine.** Identity comes from the frame and the
adapter; there is no reference list. For a character carried by references
use [`studio-media-kling`](../studio-media-kling/SKILL.md); for Wan without
weights use [`studio-media-wan-2-6-i2v`](../studio-media-wan-2-6-i2v/SKILL.md).
