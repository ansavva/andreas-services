---
name: studio-media-wan-2-6-i2v
description: Animate one still into video with Alibaba's Wan 2.6 image-to-video (runpod/wan-2-6-i2v) on Runpod's public endpoint as a recorded run — an open-weight engine at a per-second price with a real negative prompt and a repeatable seed. Use when a clip must open on a chosen frame (the frame-first workflow), when a character's identity is already in a still and no reference set is needed, or as the untrained baseline the character-LoRA comparison is scored against. 5/10/15 s at 720p or 1080p landscape. For a clip from words alone use studio-media-wan-2-6-t2v.
---

# studio-media-wan-2-6-i2v

`runpod/wan-2-6-i2v` — Wan 2.6 image-to-video, Alibaba's open-weight video
model, served by **Runpod's public endpoint** rather than Replicate. One
still in, a 5/10/15-second clip out that opens on that frame, at 720p or
1080p landscape. The same controls as its text-to-video sibling — a real
negative prompt, a seed, `shot_type` — over a start frame, which is where
identity comes from: this model has **no reference list**.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model wan-2.6-i2v …`,
> and `studio models show wan-2.6-i2v` for the schema. This page covers
> only what is specific to this model.

## What is specific to this model

| | |
|---|---|
| Provider | **Runpod**, not Replicate — the registry entry says `provider: runpod`, the API holds a Runpod key beside its Replicate token, and the run's `cost.amount` is a real price. Nothing about the commands changes |
| Schema | Runpod publishes none, so the registry entry **is** the schema: `studio models show` prints it from there, and submit validates against it |
| Images field | **one start frame, required**: `image`, bound with `--start-run` / `--start-key`. No reference list (`--character`, `--ref-run`, `--key` are refused) and no end frame |
| Accepts | `.jpg .jpeg .png .webp` |
| Duration | `duration` — `5` (default), `10`, `15` seconds |
| Size | `size` — `1280*720` (default) or `1920*1080`. Landscape only; no aspect-ratio field, so `--aspect-ratio` does not apply |
| Shot type | `shot_type` — `single` (default) or `multi` |
| Negative | `negative_prompt` — a real parameter, honoured |
| Seed | `seed` — `-1` (default) is random; any other integer repeats the draw |
| Prompt expansion | `enable_prompt_expansion` — off by default |
| Safety checker | `enable_safety_checker` — on by default; the endpoint's own content check over the output |
| Price | **per second of output** (Runpod, September 2026): **$0.10/s at 720p, $0.15/s at 1080p** — a 5 s 720p clip is $0.50, 15 s at 1080p is $2.25. The run records what it charged |
| Not here | no reference images, no end frame, no audio input (the endpoint's `audio` URL is not wired — studio binds nodes, never URLs), no step count |

## Invoke

```bash
# animate the last image run's output, five seconds at 720p
studio run --model wan-2.6-i2v --project <project> \
  --start-run <project>/latest#1 \
  --extra '{"duration":5,"size":"1280*720","seed":7}' \
  --prompt "…"

# a named still, ten seconds at 1080p
studio run --model wan-2.6-i2v --project <project> \
  --start-key <node> \
  --extra '{"duration":10,"size":"1920*1080"}' \
  --prompt "…"
```

The still's aspect should match the size asked for — a portrait frame into a
`1280*720` clip is the model's to crop, and it will. Render the frame at
16:9 first, or accept the crop deliberately.

## Prompting

Describe the **motion**, not the frame: the frame is already there. What
moves, how the camera moves, what changes by the end. A prompt that
re-describes the still's contents spends its words on what the model can
see, and a prompt that contradicts them — a different wardrobe, a different
setting — asks for a clip that drifts off its own first frame.

## What it is for, and what it is not

**For:** the frame-first workflow — a still rendered on-model by an image
engine, then given motion here — at an open-weight, per-second price; and
the untrained baseline in the character-LoRA comparison, where the same
frame and seed run before and after training.

**Not a reference-image engine.** Identity is whatever the start frame
holds and nothing more. For a character carried by a reference set into a
new composition use [`studio-media-kling`](../studio-media-kling/SKILL.md) or
[`studio-media-seedance-2-5`](../studio-media-seedance-2-5/SKILL.md). For a
clip that needs no frame at all use
[`studio-media-wan-2-6-t2v`](../studio-media-wan-2-6-t2v/SKILL.md).
