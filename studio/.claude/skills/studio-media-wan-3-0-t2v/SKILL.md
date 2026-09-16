---
name: studio-media-wan-3-0-t2v
description: Generate video from text alone with Alibaba's Wan 3.0 (fal/alibaba/wan-3.0/text-to-video) on fal.ai's queue API as a recorded run — the newest Wan, the first model here on fal (the third provider), and the imageless engine with native audio, any length from 2 to 30 seconds and five aspect ratios. Use when a clip is described in words and needs no start frame or character identity, when a longer-than-15-second single take is wanted without chaining, or when the clip should arrive with its own soundtrack. Per second at 480p/720p/1080p. For a clip that must open on a chosen still use studio-media-wan-3-0-i2v; for a character on-model from reference images use studio-media-wan-3-0-r2v.
---

# studio-media-wan-3-0-t2v

`fal/alibaba/wan-3.0/text-to-video` — Wan 3.0, Alibaba's current video
model, served by **fal.ai** rather than Replicate or Runpod: in September
2026 fal is the only one of the three hosting it. Text in, a clip of any
integer length from 2 to 30 seconds out, at 480p, 720p or 1080p, in any of
five aspect ratios, **with audio generated in the same pass**. It takes no
image of any kind.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model wan-3.0-t2v …`,
> and `studio models show wan-3.0-t2v` for the schema. This page covers
> only what is specific to this model.

## What is specific to this model

| | |
|---|---|
| Provider | **fal.ai** — the registry entry says `provider: fal`, the API holds a fal key beside its Replicate and Runpod ones, and the run records **no price**: fal's body carries none, and studio does not multiply one out. Nothing about the commands changes |
| Schema | **Live**, like Replicate's: fal publishes an OpenAPI document per endpoint, and `studio models show` / `models refresh` read it. Unlike Runpod, the entry carries no schema of its own |
| Images | **none.** No reference list, no start frame, no end frame. `--character`, `--ref-run`, `--start-run`, `--key` are all refused. For a start frame use [`studio-media-wan-3-0-i2v`](../studio-media-wan-3-0-i2v/SKILL.md); for references, [`studio-media-wan-3-0-r2v`](../studio-media-wan-3-0-r2v/SKILL.md) |
| Duration | `duration` — any integer **2–30** seconds (default 5), or `null` to let the model pick a length from the prompt |
| Resolution | `resolution` — `480p`, `720p`, `1080p`. **Studio defaults it to 720p**; fal's own default is 1080p, at twice the price |
| Aspect | `aspect_ratio` — `adaptive` (default), `16:9`, `4:3`, `1:1`, `3:4`, `9:16` |
| Audio | `audio` — **on by default**: a soundtrack generated with the picture. Off for a silent clip |
| Seed | `seed` — an integer, 0 to 2³¹−1; omit for a random draw. The one used comes back on the run's response |
| Prompt expansion | `enable_prompt_expansion` — **on by default, deliberately**, unlike the Wan 2.6 entries: fal says turning it off "is likely to degrade generation quality". The rewritten prompt comes back as `actual_prompt` in the stored response, so what the model actually saw is on the record |
| Thinking | `enable_thinking` — off; on, a reasoning pass before generation, at a latency cost |
| Negative | **no field.** Keep-outs go in the prompt, as on Kling and Seedance |
| Price | **per second of output** (fal, September 2026): **$0.05/s** at 480p, **$0.10/s** at 720p, **$0.20/s** at 1080p — a 5 s clip is $0.25 / $0.50 / $1.00, a 30 s clip at 1080p is $6.00. The run's `cost.amount` stays null; the bill is fal's dashboard |
| Not here | no images, no negative prompt, no shot-type switch (the prompt cuts, if it cuts), no step count |

## Invoke

```bash
# five seconds, 720p, landscape, a repeatable seed
studio run --model wan-3.0-t2v --project <project> \
  --extra '{"duration":5,"aspect_ratio":"16:9","seed":7}' \
  --prompt "…"

# a fifteen-second portrait clip, silent, at 1080p
studio run --model wan-3.0-t2v --project <project> \
  --extra '{"duration":15,"resolution":"1080p","aspect_ratio":"9:16","audio":false}' \
  --prompt "…"
```

A video run returns as soon as it is submitted and closes on its own;
`--poll` waits. `studio runs show <run>` reads it back either way.

## Prompting

One sentence of subject, one of action, one of camera, one of light — and,
because the model writes the sound, one of what is heard. Prompt expansion
is on, so a terse prompt is filled out before rendering; read
`actual_prompt` off the stored response when a result surprises, and lock
the seed before iterating on the words.

## What it is for, and what it is not

**For:** blocking out a shot idea before a dearer engine renders it
on-model, establishing shots and plates with no character in them, a single
take longer than 15 seconds without [`studio-media-scene`](../studio-media-scene/SKILL.md)'s
chaining, and a clip that should arrive with its own sound.

**Not for holding a character on-model.** There is no image input, so
nothing can carry identity. A character clip is
[`studio-media-wan-3-0-r2v`](../studio-media-wan-3-0-r2v/SKILL.md) from
references, [`studio-media-wan-3-0-i2v`](../studio-media-wan-3-0-i2v/SKILL.md)
from a still that already holds the likeness, or
[`studio-media-kling`](../studio-media-kling/SKILL.md) /
[`studio-media-seedance-2-5`](../studio-media-seedance-2-5/SKILL.md).
