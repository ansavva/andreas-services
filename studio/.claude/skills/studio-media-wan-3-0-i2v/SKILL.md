---
name: studio-media-wan-3-0-i2v
description: Animate one still into video with Alibaba's Wan 3.0 image-to-video (fal/alibaba/wan-3.0/image-to-video) on fal.ai's queue API as a recorded run — a required start frame, an optional end frame to land on, native audio, any length from 2 to 30 seconds. Use when a clip must open on a chosen frame (the frame-first workflow), when it must also close on one, when a character's identity is already in a still and no reference set is needed, or when a continuation clip needs more than 15 seconds in one pass. Per second at 480p/720p/1080p. For a clip from words alone use studio-media-wan-3-0-t2v; for references instead of a frame, studio-media-wan-3-0-r2v.
---

# studio-media-wan-3-0-i2v

`fal/alibaba/wan-3.0/image-to-video` — Wan 3.0 from a still, on **fal.ai**.
One required start frame, an optional last frame, a clip of 2–30 seconds
that opens on the first and — when given — lands on the second, with audio
generated in the same pass. The frame-first workflow every other video
engine here uses, plus the first-and-last interpolation only Veo and Seedance
also offer.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model wan-3.0-i2v …`,
> and `studio models show wan-3.0-i2v` for the schema. Everything about
> provider, price, duration, resolution, aspect, audio, seed, prompt
> expansion and thinking is as on [`studio-media-wan-3-0-t2v`](../studio-media-wan-3-0-t2v/SKILL.md);
> this page covers only what differs.

## What is specific to this model

| | |
|---|---|
| Start frame | `start_image_url` — **required.** Bound with `--start-run <run>` (its first output) or `--start-key <node>`; jpg/png/webp. The clip opens on it |
| End frame | `end_image_url` — optional. `--end-run` / `--end-key`. The clip lands on it; the model interpolates between the two |
| References | **none.** Identity comes from the frame. For a reference set use [`studio-media-wan-3-0-r2v`](../studio-media-wan-3-0-r2v/SKILL.md) |
| Aspect | `aspect_ratio: adaptive` (default) follows the start frame; a named ratio reframes it |
| Price | as t2v — per second by resolution; the frames cost nothing extra |

## Invoke

```bash
# animate the first output of a still run, five seconds at 720p
studio run --model wan-3.0-i2v --project <project> \
  --start-run <project>/<still-run> \
  --extra '{"duration":5}' \
  --prompt "…"

# open on one frame and land on another
studio run --model wan-3.0-i2v --project <project> \
  --start-run <project>/<frame-a> --end-run <project>/<frame-b> \
  --extra '{"duration":8,"resolution":"1080p"}' \
  --prompt "…"
```

## Prompting

The prompt describes **motion**, not the frame — the frame is already
there. Say what moves, how the camera moves, and what is heard. Anything
in the prompt that contradicts the still is a fight the still usually
wins. With an end frame, describe the path between the two rather than
either endpoint.

## Where it sits

The continuation engine of the Wan family: a
[`studio-media-scene`](../studio-media-scene/SKILL.md) chain renders each
clip from the previous clip's last frame, and this is the model that takes
that frame. Against [`studio-media-wan-2-6-i2v`](../studio-media-wan-2-6-i2v/SKILL.md)
it adds an end frame, any length to 30 s, portrait, audio, and loses the
negative prompt.
