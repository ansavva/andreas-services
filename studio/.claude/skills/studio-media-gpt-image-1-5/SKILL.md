---
name: studio-media-gpt-image-1-5
description: Render still images with OpenAI's GPT Image 1.5 (openai/gpt-image-1.5) on Replicate as a recorded run. The GPT Image model that does TRANSPARENT BACKGROUNDS and exposes an explicit input_fidelity knob (dial face preservation up or down). Use when a frame needs a transparent PNG, or when fidelity to the input images must be controlled rather than automatic. Otherwise prefer the newer studio-media-gpt-image-2.
---

# studio-media-gpt-image-1-5

`openai/gpt-image-1.5` — the previous OpenAI flagship. Superseded by
[`gpt-image-2`](../studio-media-gpt-image-2/SKILL.md) for most work, but it keeps two
capabilities its successor dropped, and those are the reason to choose it.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model gpt-image-1.5 …`,
> and `studio models show gpt-image-1.5` for the live schema. This page covers
> only what is specific to this model. [`gpt-image-2`](../studio-media-gpt-image-2/SKILL.md) is the newer sibling.

## Why you would pick this over `gpt-image-2`

**1. Transparent backgrounds.** `background: "transparent"` genuinely works
here. `gpt-image-2` lists the value in its schema but does not support it, and
its own docs redirect to this model.

**2. An explicit `input_fidelity` knob** — `low` (default) or `high`:

> Control how much effort the model will exert to match the style and features,
> especially facial features, of input images

`gpt-image-2` holds inputs at high fidelity *automatically* with no knob, so it
cannot be dialled **down**. If you want the model to take liberties with a
reference rather than reproduce it, this is the only GPT Image that will.

Note the default is `"low"` — for identity work you must ask for it:

```bash
--extra '{"input_fidelity":"high","quality":"high"}'
```

## What is specific to this model

| | |
|---|---|
| Images field | `input_images`, no documented cap |
| Accepts | `.jpg .jpeg .png .webp` |
| Output | **`webp` default**, `png`, `jpeg` |
| Aspect | **only `1:1`, `3:2`, `2:3`** — far narrower than gpt-image-2 |
| `input_fidelity` | `low` (default) / `high` |
| Background | `auto` / `opaque` / **`transparent`** |
| Moderation | `auto` (default) / `low` |

**The aspect list is the trap.** Three values only. A `9:16` portrait — legal on
every other model in the harness — is rejected here:

```
error: openai/gpt-image-1.5: aspect_ratio='9:16' is not one of ['1:1', '3:2', '2:3']
```

That is caught locally before anything bills. Use `2:3` for portrait, `3:2` for
landscape, or switch to `gpt-image-2`, which takes `9:16` and explicit pixel
sizes.

## Output format

`.webp` by default, so ask for `png` if the frame is headed for Kling as a start
frame — see [`studio-media-gpt-image-2`](../studio-media-gpt-image-2/SKILL.md#output-format--convert-before-handing-a-frame-to-kling).
