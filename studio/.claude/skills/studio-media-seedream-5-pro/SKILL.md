---
name: studio-media-seedream-5-pro
description: Render still images with ByteDance's Seedream 5.0 Pro (bytedance/seedream-5-pro) on Replicate as a recorded run. Use when a frame blends several references into one composition — up to 10 images for character, product or style consistency — or when a flat, known per-image price matters more than resolution. Hard 2K ceiling and no text-rendering claim. For a character frame the default is still studio-media-gpt-image-2; for 4K or legible text use studio-media-nano-banana-pro.
---

# studio-media-seedream-5-pro

`bytedance/seedream-5-pro` — ByteDance's flagship still model, and the image
sibling of Seedance. What it does that the others do not sell: **multi-image
composition** — up to 10 references guiding one result, to hold a character, a
product or a style, or to put several subjects into one scene. It bills a flat
price per output image, decided by resolution alone.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model seedream-5-pro …`,
> and `studio models show seedream-5-pro` for the live schema. This page covers
> only what is specific to this model. [`seedance`](../studio-media-seedance/SKILL.md)
> is the video engine from the same house.

## What is specific to this model

| | |
|---|---|
| Images field | `image_input`, **≤10** |
| Accepts | `.jpg .jpeg .png .webp` — the README names no formats; this is the common set, and a rejection at submit is the signal it is narrower |
| Output | **`png` default** or `jpeg` |
| Resolution | `size`: `1K` (~2 MP) / **`2K` default** (~4 MP, up to 2048×2048) — **no 4K** |
| Aspect | `match_input_image` (default) + `1:1` `4:3` `3:4` `16:9` `9:16` `3:2` `2:3` `21:9` |
| Prompt | **≤4000 characters** — the only image model here with a stated cap, enforced before submit |
| Price | flat per image: 1K $0.045, 2K $0.09 (docs, September 2026) |
| Not here | no seed, no negative prompt, no quality tier, no safety knob — the prompt and the references are the only levers |

## Invoke

```bash
studio run --model seedream-5-pro --project <project> \
  --character <name> --pick-tag face \
  --aspect-ratio 3:4 \
  --prompt "…"
```

## `match_input_image` with no image — pass an aspect ratio

The default aspect is `match_input_image`, which takes its shape from the
**first** reference. The docs say nothing about what the model does with that
default and no image at all, so a `--no-refs` generation should always carry an
explicit `--aspect-ratio`. With references, the order is load-bearing for the
frame's shape as well as its content: put the image whose framing you want
first.

## `size` — two values the schema lists that a still cannot use

The live schema offers `size` as `1K` / `1.5K` / `2K` / `auto`. The field's own
description says standard generation supports **only `1K` and `2K`**; `1.5K`
and `auto` belong to layer-decomposition mode, below. A value that validates
and is then not honoured is worse than one that errors, so both are recorded
under `denied` and rejected before submitting:

```
error: bytedance/seedream-5-pro: size='1.5K' — seedream-5-pro renders standard
images at 1K or 2K only; 1.5K exists for layer_decomposition mode (its schema
lists it for both).
```

## Layer decomposition — a different job, not a frame

`layer_decomposition: true` splits **exactly one** input image into a base
image plus up to 16 element layers, each a PNG with a name, bounding box and
stacking order. It is an editing tool, not a generator: the prompt becomes
optional and names which elements to split out. Nothing in the frame-first
workflow wants it, and a run made this way would carry up to 17 outputs. Reach
it only deliberately, with `--extra '{"layer_decomposition": true}'` and a
single `--key`; the `size` denial above still applies, so a layer run uses `1K`
or `2K`.

## Choosing between it and the others

- **A character frame to animate** — [`gpt-image-2`](../studio-media-gpt-image-2/SKILL.md)
  is still the default; its references are held at high fidelity automatically.
- **Several references into one scene** — this model. It takes 10 where GPT
  Image states no cap and Nano Banana Pro takes 14, but composition is what its
  docs lead with. Choose the subset with `--pick` / `--pick-tag` rather than
  sending a pool whole: past a handful, every added reference dilutes the one
  that matters.
- **4K, or legible text** — [`nano-banana-pro`](../studio-media-nano-banana-pro/SKILL.md).
  This model stops at 2K and makes no claim about text. For a 2K frame that
  needs to be bigger, enlarge it after with
  [`image-upscale`](../studio-media-image-upscale/SKILL.md) rather than
  re-rendering elsewhere.
- **A transparent PNG** — [`gpt-image-1.5`](../studio-media-gpt-image-1-5/SKILL.md).
  There is no background control here.

Do not confuse this model with `bytedance/seedream-5`, the model Nano Banana
Pro's `allow_fallback_model` reroutes to. That is a separate Replicate model
with its own price and is not registered here.

## Handing a frame onward

Output is `png` by default, which every video engine here accepts, so a
seedream still goes to Kling or Seedance without conversion. The other way
round — a `.webp` from GPT Image 2 as a reference for this model — is fine
under the accepted list above; if the provider rejects it, convert first:

```bash
studio convert --run <project>/latest#1 --for seedream-5-pro --add-input <project>
```

## When the output goes wrong

- **The wrong subject dominates.** Reference order and count. Lead with the
  image that should win, and cut the set — `--pick` a face and one outfit
  rather than the whole pool.
- **The frame is the wrong shape.** `match_input_image` followed the first
  reference. Pass `--aspect-ratio` explicitly.
- **Soft or small.** You are on `1K`; the default is `2K`, so something set it.
  Check the payload before blaming the model.
- **A prompt refused before submit.** It is over 4000 characters — trim it;
  nothing is sent.
