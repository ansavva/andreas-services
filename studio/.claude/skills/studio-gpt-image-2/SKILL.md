---
name: studio-gpt-image-2
description: Render still images with OpenAI's GPT Image 2 (openai/gpt-image-2) on Replicate as a recorded run. OpenAI's newest image model — strongest instruction-following and text rendering, the widest aspect list including explicit pixel sizes, and reference images held at high fidelity automatically. Use when a frame needs dense legible text, precise edits that preserve identity, or a non-standard output size. Cannot do transparent backgrounds — for those use studio-gpt-image-1-5.
---

# studio-gpt-image-2

`openai/gpt-image-2` — OpenAI's newest image model, and the most capable of the
two GPT Image entries. No OpenAI key needed; it bills through Replicate.

> Invocation, the approval gate, run recording and validation are shared —
> see [`studio-core`](../studio-core/SKILL.md): `studio.py run --model gpt-image-2 …`,
> and `studio.py models show gpt-image-2` for the live schema. This page covers
> only what is specific to this model. [`gpt-image-1.5`](../studio-gpt-image-1-5/SKILL.md) is the sibling that does transparent backgrounds.

## What is specific to this model

| | |
|---|---|
| Images field | `input_images`, no documented cap |
| Accepts | `.jpg .jpeg .png .webp` |
| Output | **`webp` default**, `png`, `jpeg` — note `jpeg`, not Google's `jpg` |
| Aspect | ratios, `auto`, **and explicit pixel sizes** to `3840x2160` |
| Quality | `low` / `medium` / `high` / `auto` |
| Moderation | `auto` (default) / `low` |
| Background | `auto` / `opaque` — **`transparent` is rejected locally, see below** |

## The `input_fidelity` question — it is not missing, it is always on

`gpt-image-2` has **no `input_fidelity` field**, and the obvious reading —
that it lost the ability to hold a face — is wrong. Its documentation:

> When you pass reference images, GPT Image 2 processes them at high fidelity
> automatically. There's **no knob to adjust** — the model always does its best
> to preserve the details of the input.

So for identity work this is the sensible default. Reach for
[`gpt-image-1.5`](../studio-gpt-image-1-5/SKILL.md) only when you need a
transparent background, or when you want to dial fidelity *down* (`"low"`),
which this model cannot do.

## Transparent backgrounds — the schema lies

The live schema lists `background: "transparent"`. The docs say the model does
not support it and point at `gpt-image-1.5`. A value that validates and is then
not honoured is worse than one that errors, so it is recorded under `denied` in
the registry and rejected before submitting:

```
error: openai/gpt-image-2: background='transparent' — gpt-image-2 does not
support transparent backgrounds (its schema still lists the value).
Use gpt-image-1.5 for transparent PNGs.
```

The README is stale in the other direction too: it lists three aspect ratios
where the schema has eighteen. **Trust the schema for what a field accepts, the
docs for what the model honours.**

## Output format — convert before handing a frame to Kling

This model writes **`.webp` by default**, and Kling accepts only
`.jpg/.jpeg/.png`. The submitter rejects the binding up front rather than
letting the render fail. Two ways out:

```bash
# best: ask for png at generation time
--extra '{"output_format":"png"}'

# or convert an existing run output (the source is never modified)
studio convert \
  --run <project>/latest#1 --for kling --add-input <name>
```
