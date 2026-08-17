---
name: studio-nano-banana-2
description: Render still images with Google's Nano Banana 2 (google/nano-banana-2, Gemini 3.1 Flash Image) on Replicate as a recorded run. Use for high-volume or fast iteration where Pro-level quality is not required, for the extreme 1:4/4:1/1:8/8:1 aspect ratios only this model has, or for Google Search / Image Search grounded generation. The cheap fast sibling of studio-nano-banana-pro.
---

# studio-nano-banana-2

`google/nano-banana-2` — Google's Gemini 3.1 Flash Image. The high-efficiency
counterpart to Nano Banana Pro: Pro-level visual quality at Flash speed and
price. Reach for it when iterating fast or generating in volume.

> Invocation, the approval gate, run recording and validation are shared —
> see [`studio-core`](../studio-core/SKILL.md): `studio run --model nano-banana-2 …`,
> and `studio models show nano-banana-2` for the live schema. This page covers
> only what is specific to this model. [`nano-banana-pro`](../studio-nano-banana-pro/SKILL.md) is the stronger sibling.

## What is specific to this model

| | |
|---|---|
| Images field | `image_input`, **≤14** |
| Accepts | `.jpg .jpeg .png .webp` |
| Output | `jpg` (default) or `png` |
| Resolution | **`1K` default** / `2K` / `4K` — note Pro defaults to 2K |
| Aspect | the standard set **plus `1:4`, `4:1`, `1:8`, `8:1`** |
| Grounding | `google_search`, `image_search` (both default false) |

Two things only this model has:

**Extreme aspect ratios.** `1:4`, `4:1`, `1:8`, `8:1` exist nowhere else in the
harness — banners, skyscraper crops, filmstrips.

**Search grounding.** `google_search` pulls real-time facts (weather, scores,
recent events) into the image; `image_search` finds web images as visual
context, and turns web search on implicitly. Both are off by default. Neither
belongs in character work — they introduce material you did not curate.

## Choosing between it and Pro

Default to **Pro** for a character frame that will be animated: it is the
stronger model and holds resemblance across more people. Use **2** when the
frame is a throwaway, when you are sweeping many variations, or when you need an
aspect ratio Pro does not have.

Note the resolution default differs — 2 renders at `1K` unless told otherwise,
so an unqualified comparison against Pro is not like-for-like. Pass
`--extra '{"resolution":"2K"}'` to match.

