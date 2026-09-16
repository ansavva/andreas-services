---
name: studio-media-wan-3-0-r2v
description: Generate video from up to 10 reference images with Alibaba's Wan 3.0 reference-to-video (fal/alibaba/wan-3.0/reference-to-video) on fal.ai's queue API as a recorded run — the Wan engine for a character on-model, where the prompt addresses the references positionally ("the subject in Image 1 …"). Use when a character or product must appear as itself without a pre-rendered start frame, when several references should be combined into one shot, or as the reference-driven alternative to Kling's and Seedance's reference lists. Native audio, 2–30 seconds, per second at 480p/720p/1080p. For a chosen opening frame use studio-media-wan-3-0-i2v; from words alone, studio-media-wan-3-0-t2v.
---

# studio-media-wan-3-0-r2v

`fal/alibaba/wan-3.0/reference-to-video` — Wan 3.0 steered by references,
on **fal.ai**. Up to ten reference images go in; the prompt names them by
position — *the subject in Image 1 walks past the car in Image 2* — and a
clip of 2–30 seconds comes out with audio. No start frame and no end frame:
the references carry identity, the prompt carries the shot.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model wan-3.0-r2v …`,
> and `studio models show wan-3.0-r2v` for the schema. Everything about
> provider, price, duration, resolution, aspect, audio, seed, prompt
> expansion and thinking is as on [`studio-media-wan-3-0-t2v`](../studio-media-wan-3-0-t2v/SKILL.md);
> this page covers only what differs.

## What is specific to this model

| | |
|---|---|
| References | `reference_image_urls` — a list, **up to 10**, jpg/png/webp. Bound with `--character <name>` (its described index picks the subset), `--ref-run <run>`, or `--key <node>` per image. The order is the order the prompt counts in |
| Positional prompt | the prompt addresses references as `Image 1`, `Image 2`, … in binding order. A reference the prompt never names still influences the look; naming it is what makes it *that* subject doing *that* thing |
| Start / end frame | **none.** For a chosen opening frame use [`studio-media-wan-3-0-i2v`](../studio-media-wan-3-0-i2v/SKILL.md) |
| Prompt | optional on the endpoint; studio requires one — a reference set with no direction is a guess |
| Not wired | the endpoint also takes up to 5 reference **videos** (15 s total, ≥16 fps) and 5 reference **audios** (15 s total), and a `web_url` / `file_url` to build from with `enable_thinking`. None reaches it from studio yet — studio binds image nodes, never URLs, and no clip or audio send exists for this entry. Ask before assuming they work |

## Invoke

```bash
# a character on-model, references chosen from its described index
studio run --model wan-3.0-r2v --project <project> \
  --character <name> \
  --extra '{"duration":6,"aspect_ratio":"16:9","seed":11}' \
  --prompt "The subject in Image 1 turns from the window and …"

# two explicit references, product plus setting
studio run --model wan-3.0-r2v --project <project> \
  --key <product-node> --key <setting-node> \
  --extra '{"duration":5}' \
  --prompt "The bottle in Image 1 stands on the table in Image 2 as …"
```

## Prompting

Count the references and name each one once, early: *Image 1 is the
subject, Image 2 the room.* Then the shot, as on any engine — action,
camera, light, sound. Ten references is a ceiling, not a target: three
that agree beat ten that argue, and
[`studio-media-character`](../studio-media-character/SKILL.md)'s described
index is how a subset is chosen rather than a folder sent whole.

## Where it sits

The reference-driven engine of the Wan family — what
[`studio-media-kling`](../studio-media-kling/SKILL.md)'s 7-image list and
[`studio-media-seedance-2-5`](../studio-media-seedance-2-5/SKILL.md)'s
30-image list are to theirs — and the first Wan here that can hold a
character without a rendered frame or a trained LoRA. Against
[`studio-media-wan-2-2-i2v-lora`](../studio-media-wan-2-2-i2v-lora/SKILL.md)
it is the untrained comparison: same character, references instead of
weights.
