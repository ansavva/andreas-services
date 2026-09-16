---
name: studio-media-wan-2-6-t2v
description: Generate video from text alone with Alibaba's Wan 2.6 (runpod/wan-2-6-t2v) on Runpod's public endpoint as a recorded run — the first open-weight video model in the harness, and, with wan-3.0-t2v, one of the two video engines here that take NO image. Use when a clip is described in words and needs no start frame or character identity, when a cheap fixed-price draft of a shot idea is worth more than an on-model render, or when a video must be repeatable with a seed against a real negative prompt. 5/10/15 s at 720p or 1080p, landscape or portrait, priced per clip. For a clip that must open on a chosen still use studio-media-wan-2-6-i2v; for a character on-model use Kling or Seedance.
---

# studio-media-wan-2-6-t2v

`runpod/wan-2-6-t2v` — Wan 2.6, Alibaba's open-weight video model, served by
**Runpod's public endpoint** rather than Replicate. Text in, a coherent
5/10/15-second clip out, at 720p or 1080p, landscape or portrait. Stable
motion and close instruction-following are its claims; a real negative
prompt and a repeatable seed are what set it apart from the Replicate
engines here besides Veo. **It takes no image of any kind.**

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model wan-2.6-t2v …`,
> and `studio models show wan-2.6-t2v` for the schema. This page covers
> only what is specific to this model.

## What is specific to this model

| | |
|---|---|
| Provider | **Runpod**, not Replicate — the registry entry says `provider: runpod`, the API holds a Runpod key beside its Replicate token, and the run's `cost.amount` is a real price. Nothing about the commands changes |
| Schema | Runpod publishes none, so the registry entry **is** the schema: `studio models show` prints it from there, and submit validates against it |
| Images | **none.** No reference list, no start frame, no end frame. `--character`, `--ref-run`, `--start-run`, `--key` are all refused. For a start frame use [`studio-media-wan-2-6-i2v`](../studio-media-wan-2-6-i2v/SKILL.md) |
| Duration | `duration` — `5` (default), `10`, `15` seconds, nothing between |
| Size | `size`, a fixed list of `W*H`: `1280*720` (default), `1920*1080`, `720*1280`, `1080*1920`. No aspect-ratio field — `--aspect-ratio` does not apply; portrait is a size |
| Shot type | `shot_type` — `single` (default) holds one composition; `multi` lets the model cut between shots within the clip |
| Negative | `negative_prompt` — a real parameter, honoured |
| Seed | `seed` — `-1` (default) is random; any other integer repeats the draw |
| Prompt expansion | `enable_prompt_expansion` — off by default; on, a rewriter expands the prompt before rendering, so what was read is no longer exactly what was sent |
| Price | **per clip**, by size and length (Runpod, September 2026): 720p **$0.50 / $1.00 / $1.50**, 1080p **$0.75 / $1.50 / $2.25** for 5 / 10 / 15 s. The run records what it charged |
| Not here | no images, no audio input (the endpoint's `audio` URL is not wired — studio binds nodes, never URLs), no step count, no guidance |
| Beware | the worker **ignores fields it does not know** rather than refusing them — a misspelt input renders at the default and bills. The registry's check at submit is the only gate |

## Invoke

```bash
# five seconds, landscape 720p, a repeatable seed
studio run --model wan-2.6-t2v --project <project> \
  --extra '{"duration":5,"size":"1280*720","seed":7}' \
  --prompt "…"

# portrait, ten seconds, with a negative prompt
studio run --model wan-2.6-t2v --project <project> \
  --extra '{"duration":10,"size":"1080*1920","negative_prompt":"text, watermark, jitter"}' \
  --prompt "…"
```

A video run returns as soon as it is submitted and closes on its own;
`--poll` waits. `studio runs show <run>` reads it back either way.

## Prompting

One sentence of subject, one of action, one of camera, one of light. The
model follows instructions closely, which cuts both ways: a prompt that
names two camera moves gets both. `shot_type: multi` is the right answer to
"and then cut to…", not a second clause in the prompt. Leave
`enable_prompt_expansion` off until a prompt has been tried plain — an
expanded prompt is one the person never read.

## What it is for, and what it is not

**For:** blocking out a shot idea before a dearer engine renders it on-model,
establishing shots and plates with no character in them, a fixed-price
draft of motion, and the untrained baseline in the character-LoRA
comparison — the same prompt, seed-locked, before and after training.

**Not for holding a character on-model.** There is no image input, so
nothing can carry identity. A character clip is
[`studio-media-kling`](../studio-media-kling/SKILL.md) or
[`studio-media-seedance-2-5`](../studio-media-seedance-2-5/SKILL.md), or this
model's image-to-video sibling from a still that already holds the likeness.
