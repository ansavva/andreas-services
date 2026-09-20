---
name: studio-media-wan-2-2-i2v-studio
description: Animate one still into video with Wan 2.2 14B on STUDIO'S OWN Runpod endpoint (wan-2.2-i2v-studio) — the same trained LoRA pair the public wan-2.2-i2v-lora endpoint loads, plus what that one refuses — an END FRAME, any length in frames (81 = 5 s, 121 = 7.5 s, up to 161), portrait or landscape 720p, a negative prompt, steps, guidance, shift and a repeatable seed. Use when a character LoRA clip needs to run longer than 8 s, land on a chosen frame, be portrait, or be re-rolled deterministically; use studio-media-wan-2-2-i2v-lora for the cheaper fixed 5/8 s clip. Priced by worker time, not per clip.
---

# studio-media-wan-2-2-i2v-studio

`runpod/unrxp9badsq4g2` — Wan 2.2 image-to-video (the 14B two-expert model),
served by **a Runpod serverless endpoint studio owns**: ComfyUI on a worker
we start, fp16 weights on a network volume we keep, one worker at most,
scaled to zero between jobs. It exists because the public LoRA endpoint
stops at 8 seconds, takes no end frame and no size, and cannot finish a
garment change or a long action. This one takes a **director's controls**.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model wan-2.2-i2v-studio …`,
> and `studio models show wan-2.2-i2v-studio` for the schema. LoRA
> handling is the same as [`studio-media-wan-2-2-i2v-lora`](../studio-media-wan-2-2-i2v-lora/SKILL.md);
> this page covers what is different.

## What is specific to this model

| | |
|---|---|
| Provider | **Runpod**, our endpoint — created by `studio/scripts/runpod-endpoint-up.sh`, removed by `studio/scripts/runpod-endpoint-down.sh`; the worker is `studio/worker/wan22/` |
| Schema | Runpod publishes none, so the registry entry **is** the schema |
| Start frame | `image`, required, bound with `--start-run` / `--start-key` |
| **End frame** | `end_image`, optional, bound with `--end-run` / `--end-key`. Wan 2.2's own first-last-frame conditioning: the clip is made to arrive on this frame. Without it the ending is the model's |
| **LoRAs** | `high_noise_loras` / `low_noise_loras`, each a list of `{path, scale}`, bound with `--lora-high-key` / `--lora-low-key` (repeatable), presigned at submit — never a URL (hard rule #3). `lora_scale` 0–2 is studio's one number for every `scale` |
| **Length** | `num_frames` — 4k+1, default `81` (5 s at 16 fps); `121` is 7.5 s, `161` is 10 s. Anything else rounds down. Cost scales with it; past ~121 the motion can drift and a second run from the last frame ([`studio-media-scene`](../studio-media-scene/SKILL.md)) is the better long take |
| `fps` | playback rate of the file, default 16 — Wan generates at 16; another value changes speed, not the frame count |
| Size | `width` / `height`, multiples of 16, both or neither. **Unset follows the still**: 1280x720 for a landscape frame, 720x1280 for a portrait one. A still of another aspect is centre-cropped to the size |
| Negative | `negative_prompt` — a real one; unset sends Wan's standard negative |
| **Mode** | `mode` — `quality` (default): Wan's own sampling, 20 steps, guidance 3.5, shift 8. `fast`: the Wan 2.2 Lightning 4-step distillation pair is loaded ahead of yours — 4 steps, guidance 1, shift 5 — for about a fifth of the render time and cost, with slightly flatter motion. The look to draft in; `quality` for the take |
| Sampling | `steps` (half to each expert), `guidance` (cfg), `shift` — unset takes the mode's; set one to override it |
| Seed | `seed` — `-1` random; any other integer repeats. The run's response records the seed used |
| Safety checker | none. No prompt expansion either: what was read is what was sent |
| **Price** | **by worker time**, not per clip: seconds × the GPU's flex price (H100 $0.00116/s), reported by the worker as `cost`. Measured 2026-09-20 on the serverless worker (H100): **121 frames with an end frame, quality mode, 24 min, $1.66**; the same on a dev pod with the same GPU type ran twice as fast (34 s/step against 70), which is not yet understood — the worker's README has the table. `fast` is about a third. A cold start adds ~1 min before the first job and the first model load (~1–2 min) inside it, billed too |
| Idle cost | zero. The volume holding the weights is ~$7/month |

## Invoke

```bash
# 7.5 s, portrait, the character's newest trained pair, landing on a chosen frame
studio run --model wan-2.2-i2v-studio --project <project> \
  --start-run <project>/latest#1 \
  --end-key <project>/input/last-frame.png \
  --lora-high-key "<name>/models/<pair>_high_noise.safetensors" \
  --lora-low-key  "<name>/models/<pair>_low_noise.safetensors" \
  --extra '{"num_frames":121,"seed":8}' \
  --prompt "<trigger> takes his t-shirt off, unhurried"
```

Leave `--end-*` off for a plain image-to-video. Both LoRA flags repeat; a
Wan 2.2 pair is trained together, so bind both stages.

## Prompting

As on the public endpoint: describe the motion, not the frame, and **say the
trigger word** the LoRA was trained on. With an end frame, describe the path
between the two stills rather than either of them — the frames already say
where it starts and ends.

## When to reach for it

**For:** a character-LoRA clip that has to run past 8 s, be portrait, land on
a frame, or be re-rolled on the same seed with one knob changed.

**Not for:** a quick 5 s look — the public endpoint ([`studio-media-wan-2-2-i2v-lora`](../studio-media-wan-2-2-i2v-lora/SKILL.md))
is cheaper per clip and needs no cold start. Not a reference-image engine
either: identity comes from the frame and the adapter.
