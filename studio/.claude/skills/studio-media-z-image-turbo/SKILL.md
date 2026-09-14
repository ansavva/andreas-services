---
name: studio-media-z-image-turbo
description: Render still images with Tongyi Lab's Z-Image Turbo (runpod/z-image-turbo) on Runpod's public endpoint as a recorded run — the first model here that does NOT go through Replicate. Use when a frame needs a fast, cheap, photoreal draw at a flat $0.005 whatever the size, legible English or Chinese text in the image, a repeatable seed, or a light image-to-image pass over an existing frame with `strength`. Takes no reference images, no negative prompt and no step count. For a character frame the default is still studio-media-gpt-image-2.
---

# studio-media-z-image-turbo

`runpod/z-image-turbo` — Z-Image Turbo, Tongyi Lab's distilled 6-billion-
parameter text-to-image model, served by **Runpod's public endpoint** rather
than Replicate. Eight sampling steps, a few seconds a draw, photorealism at a
size where that is unusual, **bilingual text rendering** (English and Chinese
inside the image), and a prompt enhancer that expands a short prompt before
drawing. Flat **$0.005 per image**, any size; a failed draw costs nothing.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model z-image-turbo …`,
> and `studio models show z-image-turbo` for the schema. This page covers
> only what is specific to this model.

## What is specific to this model

| | |
|---|---|
| Provider | **Runpod**, not Replicate — the registry entry says `provider: runpod`, the API holds a Runpod key beside its Replicate token, and the run's `cost.amount` is a real price. Nothing about the commands changes |
| Schema | Runpod publishes none, so the registry entry **is** the schema: `studio models show` prints it from there, and submit validates against it |
| Images field | **no reference list**. One optional `image` — a start frame — which switches the model to **image-to-image** |
| Accepts | `.jpg .jpeg .png .webp` |
| Output | one image; `png` (default), `jpeg`, `webp` |
| Size | `size`, a **fixed list of `W*H` strings**: `1024*1024` (default), `512*512`, `768*768`, `1280*1280`, `1024*768`, `768*1024`, `1280*720`, `720*1280`. No aspect-ratio field — `--aspect-ratio` does not apply |
| Strength | `strength` 0–1 (default 0.8), image-to-image only: how far the result departs from `image` |
| Seed | `seed` — `-1` (default) draws at random; any other integer repeats the draw |
| Price | **$0.005 per image, flat** (Runpod, September 2026). The output URL lasts about seven days; the run stores the bytes, so that does not matter |
| Not here | no reference images, no negative prompt, no step count, no quality tier, no transparent background |

## Invoke

```bash
# text to image — no refs, a size, a repeatable seed
studio run --model z-image-turbo --project <project> \
  --no-refs \
  --extra '{"size":"1280*720","seed":7}' \
  --prompt "…"

# image to image — one frame in, strength says how much of it survives
studio run --model z-image-turbo --project <project> \
  --start-run <project>/latest#1 \
  --extra '{"size":"1024*1024","strength":0.6}' \
  --prompt "…"
```

`--start-run` / `--start-key` bind `image`; `--character`, `--ref-run`,
`--input` and `--key` are refused, because there is no list to put them in.

## Prompting — a sentence, not a tag list

The model runs its own prompt enhancer over what it is given, and the docs
say it works better from a clear descriptive sentence than from a
comma-separated pile of keywords: the enhancer has something to expand. Say
the subject, the setting, the light and the lens in prose. Text meant to
appear in the image goes in quotes, in English or Chinese — rendering it is
one of the model's stronger claims and worth testing against the real
wording rather than taking on faith.

## What it is for, and what it is not

**For:** plates and backgrounds, posters and signage with legible text, fast
iteration on a composition before a dearer model renders the final, a
light restyle of a frame that already exists. At half a cent a draw the
cheapest way to find out whether an idea reads.

**Not for holding a character on-model.** There is no reference list and no
identity input; `image` plus a low `strength` keeps *most* of a frame, which
is not the same thing. A character frame is still
[`studio-media-gpt-image-2`](../studio-media-gpt-image-2/SKILL.md).

**Do not reach for a step count.** Turbo is distilled to eight steps and its
sampler is built around that; there is no field for more, and the docs say
more would make the output worse rather than better. Z-Image-Base is the
variant for that, and it is not registered.
