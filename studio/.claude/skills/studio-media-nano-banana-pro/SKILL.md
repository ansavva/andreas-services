---
name: studio-media-nano-banana-pro
description: Render still images with Google's Nano Banana Pro (google/nano-banana-pro, Gemini 3 Pro) on Replicate as a recorded run. Use when a frame needs legible text, 4K output, up to 14 blended reference images, or a tunable safety filter — and when a request names Nano Banana Pro. The strongest all-round image model in the harness and the usual default for character frames. For its faster/cheaper sibling see studio-media-nano-banana-2.
---

# studio-media-nano-banana-pro

`google/nano-banana-pro` — Google DeepMind's image model built on Gemini 3 Pro.
The strongest all-round choice in the harness, and the usual default for a
character frame that will be animated.

> Invocation, the approval gate, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model nano-banana-pro …`,
> and `studio models show nano-banana-pro` for the live schema. This page covers
> only what is specific to this model. [`nano-banana-2`](../studio-media-nano-banana-2/SKILL.md) is the fast/cheap sibling.

## What is specific to this model

| | |
|---|---|
| Images field | `image_input`, **≤14** |
| Accepts | `.jpg .jpeg .png .webp` |
| Output | `jpg` (default) or `png` |
| Resolution | `1K` / **`2K` default** / `4K` |
| Aspect | `match_input_image` (default) + the standard ratios to `21:9` |
| Safety | `safety_filter_level`: `block_only_high` (default, most permissive) → `block_low_and_above` |

Distinctive strengths: **legible text in many languages** (posters, mockups,
infographics), Google Search grounding for real-world facts, and professional
editing controls — relight, recolour, change camera angle, adjust depth of field.

Docs put a real limit on identity work that the schema does not state: it holds
**resemblance for up to 5 people** in one composition. Every image carries an
invisible SynthID watermark.

## `allow_fallback_model` — do not set it to escape a rate limit

Nano Banana Pro is popular and hits capacity. `allow_fallback_model: true`
reroutes to **`bytedance/seedream-5`** — a *different model* than the one
approved, billed at its own price.

That makes it an approval-gate violation, not a retry knob. On `E003
ModelRateLimitError` the payload is fine: retry it **unchanged**, or switch model
deliberately. The limit can persist — five consecutive rejections inside a
ten-minute window, minutes after succeeding.

## Ordering multiple image inputs

When editing one image against others, **order is load-bearing**: base image
first, references after, and name the roles in the prompt rather than trusting
inference.

```bash
studio run --model nano-banana-pro --project <project> --slug <slug> \
  --key <name>/reference/face/<file>.png \
  --key <name>/reference/face/<other>.png \
  --aspect-ratio match_input_image \
  --prompt "Use the FIRST image as the base; take the jacket from the SECOND…"
```

Use `--pick` / `--pick-tag` to name a subset rather than passing raw `--key`s —
the bible's index says what each image shows. `--character` on its own sends the
character's `default_set`, and REFUSES rather than truncating if a selection
exceeds the 14 cap. That matters on a
large one.
