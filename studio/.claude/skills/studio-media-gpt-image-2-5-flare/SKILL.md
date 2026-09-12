---
name: studio-media-gpt-image-2-5-flare
description: Render and edit still images with OpenAI's GPT Image 2.5 Flare (openai/gpt-image-2.5-flare) on Replicate as a recorded run. The FAST sibling of studio-media-gpt-image-2-5-sunburst — identical inputs, quality tiers and per-tier prices, tuned for speed and high-volume everyday generation rather than editing precision. Use for drafts, iteration and batches; pay for Sunburst when one edit must be exact. Priced per quality tier and `auto` bills at the xhigh rate, so the registry defaults quality to medium.
---

# studio-media-gpt-image-2-5-flare

`openai/gpt-image-2.5-flare` — "OpenAI's fastest model for high-quality,
everyday image generation." It is the other half of the GPT Image 2.5 line:
the same inputs, the same six quality tiers and the same prices as
[`gpt-image-2.5-sunburst`](../studio-media-gpt-image-2-5-sunburst/SKILL.md),
tuned for speed and volume where Sunburst is tuned for editing precision.
No OpenAI key needed; it bills through Replicate.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model gpt-image-2.5-flare …`,
> and `studio models show gpt-image-2.5-flare` for the live schema. This page
> covers only what is specific to this model — which is mostly what it shares
> with Sunburst, and the one thing it does not.

## What is specific to this model

| | |
|---|---|
| Images field | `input_images`, no documented cap |
| Accepts | `.jpg .jpeg .png .webp` — the README names no formats; this is the common set |
| Output | **`webp` default**, `png`, `jpeg` |
| Aspect | ratios, `auto`, explicit pixel sizes to `3840x2160`; above 2560x1440 is experimental |
| Quality | `low` / **`medium`** (registry default) / `high` / `xhigh` / `max` / `auto` |
| Moderation | `auto` / **`low`** (registry default) |
| Background | `auto` / `transparent` / `opaque` — transparent endorsed by the README |
| Price | per output image, by tier: `low` $0.012 · `medium` $0.047 · `high` $0.128 · `xhigh` $0.25 · `max` $0.50 · **`auto` $0.25** (Replicate, September 2026) |

Every row is identical to Sunburst's, prices included. **The two differ in
speed and in what the tuning favours, and in nothing the schema can see.**

## Flare or Sunburst

The READMEs are the same document with two sentences changed. Sunburst's:
"tuned for workflows where editing precision matters most." Flare's: "the
fast option … tuned for high-volume, everyday generation where speed
matters." So:

| Job | Model |
|---|---|
| A batch of variations, a contact sheet of options, a storyboard's rough panels | **Flare** |
| Iterating a prompt one word at a time | **Flare**, on `low` |
| One edit that must change exactly one thing and leave the rest alone | Sunburst |
| The frame that ships, on `xhigh` or `max` | Sunburst |
| A fresh character frame | neither — [`gpt-image-2`](../studio-media-gpt-image-2/SKILL.md) stays the default |

Since the prices match, Flare is never the *cheaper* choice, only the faster
one — the saving is wall-clock on a run of ten, not money.

## Invoke

```bash
studio run --model gpt-image-2.5-flare --project <project> \
  --no-refs --aspect-ratio 16:9 \
  --extra '{"quality":"low","output_format":"png"}' \
  --prompt "…"
```

## `auto` quality bills at the `xhigh` rate

The schema's default `quality` is `auto`, which Replicate prices at $0.25 —
the same as `xhigh` and twenty times `low`. The registry defaults `quality`
to `medium` so a run never inherits that silently; `--extra` overrides it,
and the payload shows which tier is about to bill. On a model whose whole
point is volume, draft on `low`.

## Editing, transparency and output format

Identical to Sunburst; the prose is on
[that page](../studio-media-gpt-image-2-5-sunburst/SKILL.md) and is not
repeated here. In short: name the change and lock the rest; `transparent` is
honoured (ask for `png`); `.webp` is the default output, and Kling refuses it —
request `png` at generation time or `studio convert --for kling` afterwards.

## When the output goes wrong

- **An edit reinterpreted more than asked.** Add the lock ("change only …;
  preserve …"). If it still drifts, this is the case Sunburst is tuned for.
- **The bill was $0.25 for a draft.** `quality` was `auto` via `--extra`. The
  registry default is `medium`; drafts want `low`.
- **Ten variations came back too alike.** Vary the prompt, not the tier;
  there is no seed on this model.
