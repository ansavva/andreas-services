---
name: studio-media-ltx-2-3-i2v-lora
description: Animate one still into video with Lightricks' LTX-2.3 22B WHILE LOADING YOUR OWN LoRA (fal-ai/ltx-2.3-22b/image-to-video/lora) on fal.ai, as a recorded run — the second model in the harness that takes weights that are not its own, and the one that takes a single file rather than Wan's pair. Use when a clip must carry an LTX-2.3 character LoRA from ltx-2.3-lora-train, and for the evaluation of one. A LoRA is a .safetensors node in the library bound with --lora-key, never a pasted URL. Length in frames at 24 fps; priced per megapixel of output.
---

# studio-media-ltx-2-3-i2v-lora

`fal/fal-ai/ltx-2.3-22b/image-to-video/lora` — LTX-2.3 22B image-to-video
on **fal's queue API**, loading **LoRA weights you hand it**. LTX is one
transformer, so where Wan 2.2 takes a pair per stage this takes one list,
`loras`, and a trained LTX-2.3 LoRA is one file. `ltx-2-i2v-lora` is an
alias; the `ltx-2` and `ltx-2-19b` endpoints it might have named are
deprecated on fal since 2026-08-15, and this is the 2.3 endpoint on purpose.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model fal-ltx-2.3-i2v-lora …`,
> and `studio models show fal-ltx-2.3-i2v-lora` for the live schema. This page
> covers only what is specific to this model.

## What is specific to this model

| | |
|---|---|
| Provider | **fal**; the schema is fal's live OpenAPI document, as for the Wan 3.0 entries |
| Images | **one start frame, required**: `image_url`, bound with `--start-run` / `--start-key`; an optional end frame, `end_image_url`, with `--end-run` / `--end-key`. No reference list |
| **LoRA** | `loras`, a list of `{path, scale}`. **A LoRA is a send**: a `.safetensors` node in the library, bound with `--lora-key` (repeatable), presigned at submit — the same rule every image follows (hard rule #3). A URL in the payload is refused. `--lora-high-key` / `--lora-low-key` are Wan's and are refused here by name |
| LoRA scale | `lora_scale` 0–4 (default 1) — **studio's one number**, written into every adapter's `scale`; the endpoint never sees the name |
| Length | `num_frames` at `fps` (24): **121 is 5 s** (the default), 193 is 8 s. The endpoint rounds to 8n+1 |
| Size | `video_size: auto` follows the frame — a 9:16 still gives a 9:16 clip. No resolution field to pick |
| Audio | `generate_audio` — the model makes a soundtrack; studio's default turns it **off** for a character test |
| Prompt expansion | `enable_prompt_expansion` — studio's default turns it **off**, so the trigger word reaches the model as written |
| Negative prompt | `negative_prompt`, with a long default of fal's own (`news broadcast, 3d animation, … slowmo, static`) |
| Seed | `seed` — repeats a draw |
| Price | **per megapixel of output** — width × height × frames — at **$0.001805/MP** (fal, September 2026): a 5 s 720p clip is ~$0.20, 8 s ~$0.32; `auto` on a 1152×2048 still answered 1056×1920, so 5 s of that is ~$0.44. fal's body carries no price, so `cost.amount` stays null; fal's dashboard is the bill |
| Camera LoRAs | `camera_lora` — fal's own dolly/jib adapters, `none` by default; `camera_lora_scale` for its strength |

## Invoke

```bash
# the newest full-body still, the final checkpoint of a training run
studio run --model fal-ltx-2.3-i2v-lora --project <project> \
  --start-run <project>/latest#1 \
  --lora-key <name>/models/<name>-ohwx-pt-<run>.safetensors \
  --extra '{"num_frames":121,"seed":7,"lora_scale":1.0}' \
  --prompt "ohwx_pt turns his head to look over his left shoulder, then back to camera and smiles."
```

`--lora-key` repeats: two adapters go out as two objects with the same
`lora_scale`.

## Prompting

Describe the motion, not the frame, and **say the trigger word the LoRA was
trained on** — with prompt expansion off, what is written is what the model
reads. A LoRA with no trigger in the prompt is loaded and barely used.

## What the first clips showed (2026-09-20)

The final checkpoint of a 1500-step run, `lora_scale 1`, seed 7, 121 frames,
from a full-body still: the face held through both clips and matched the
still at the last frame; *takes his t-shirt off* finished cleanly inside
5 s with the body consistent with the frame; *turns his head over his
left shoulder, then back to camera and smiles* became a smaller head turn
the other way, ending in profile with the camera crept in — the action
read loosely. The same prompt at `lora_scale 0` turned the whole body and
came back smiling, closer to the words but a more generic face. So at
scale 1 the adapter costs some prompt adherence on motion; try 0.6–0.8
before rewriting the prompt. No wardrobe or background bleed from the
dataset in any clip.

## What it is for

The destination of an LTX-2.3 character LoRA: the same frame, prompt and
seed with each checkpoint, and once at `lora_scale 0` as the untrained
baseline, is how a training run is scored. For the same comparison on Wan
2.2 use [`studio-media-wan-2-2-i2v-lora`](../studio-media-wan-2-2-i2v-lora/SKILL.md);
for LTX without weights there is no entry yet.
