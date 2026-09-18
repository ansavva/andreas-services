---
name: studio-media-wan-3-0-openrouter
description: Generate video with Alibaba's Wan 3.0 through OpenRouter (openrouter/alibaba/wan-3.0) as a recorded run — the same model as the fal wan-3.0 entries on a fourth provider that routes it straight to Alibaba at a discount and reports the real price on the run. One entry for two modes, text-to-video and image-to-video from an optional first frame; native audio, 2 to 30 seconds, five aspect ratios, a seed. Use when the clip needs no end frame, no references and no negative prompt and price matters — or to compare what a run costs here against fal. For an end frame use studio-media-wan-3-0-i2v; for references, studio-media-wan-3-0-r2v; both stay on fal.
---

# studio-media-wan-3-0-openrouter

`openrouter/alibaba/wan-3.0` — Wan 3.0, Alibaba's current video model,
reached through **OpenRouter** rather than fal: the same weights on
Alibaba's own servers, resold at list price with a discount OpenRouter
advertises on this route, and with **the price charged written on the run**.
Text in, or text plus one still to open on; a clip of any integer length
from 2 to 30 seconds out, at 480p, 720p or 1080p, in five aspect ratios,
with audio generated in the same pass. It sits beside the three fal entries,
not in place of them.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model wan-3.0-openrouter …`,
> and `studio models show wan-3.0-openrouter` for the schema. This page covers
> only what is specific to this model.

## What is specific to this model

| | |
|---|---|
| Provider | **OpenRouter** — the registry entry says `provider: openrouter`, the API holds an OpenRouter key beside its other three, and the run records **a real price**: OpenRouter's body carries `usage.cost`, the dollars it charged. Nothing about the commands changes |
| One entry, two modes | OpenRouter has one slug for Wan 3.0, so this is one entry: no image bound is text-to-video, a `first_frame` bound is image-to-video. fal has an endpoint per mode and an entry per endpoint |
| Images | one optional **`first_frame`** — a start frame, bound with `--start-run` / `--start-key`. **No end frame and no reference list**: OpenRouter's card for this model lists `first_frame` only. `--end-run`, `--character`, `--ref-run`, `--key` are refused |
| Schema | **Live and synthesised**: OpenRouter publishes a capability card per video model rather than a schema, and `studio models show` / `models refresh` read the card. A knob the card does not name is one OpenRouter does not forward |
| Duration | `duration` — any integer **2–30** seconds. **Studio defaults it to 5**; there is no "let the model pick" here |
| Resolution | `resolution` — `480p`, `720p`, `1080p`. **Studio defaults it to 720p** |
| Aspect | `aspect_ratio` — `16:9`, `4:3`, `1:1`, `3:4`, `9:16`. No `adaptive`: with a first frame, say the frame's ratio |
| Audio | `generate_audio` — **on by default**. Off for a silent clip |
| Seed | `seed` — an integer; omit for a random draw. OpenRouter says determinism "is not guaranteed for all providers" |
| Negative | **no field**, and no prompt-expansion or thinking switch either: OpenRouter forwards no passthrough parameters for this model. Keep-outs go in the prompt |
| Price | **list price per second of output** (OpenRouter, September 2026): **$0.05/s** at 480p, **$0.10/s** at 720p, **$0.20/s** at 1080p — the same list as fal — with a **15% discount** OpenRouter advertises on the route that its card does not print. **Measured 2026-09-18**: a 2 s 480p clip cost **$0.2125** = 5 s × $0.05 × 0.85 — the discount is real, and a clip is **billed as at least 5 seconds**, so ask for 5 or more. The run's `cost.amount` is what was charged. OpenRouter is prepaid credits, no subscription; a 5.5% + $0.80 fee on each top-up |
| Not here | no end frame, no references, no negative prompt, no prompt-expansion switch, no `adaptive` ratio, no shot-type switch |

## Invoke

```bash
# text to video — five seconds, 720p, landscape, a repeatable seed
studio run --model wan-3.0-openrouter --project <project> \
  --no-refs \
  --extra '{"duration":5,"aspect_ratio":"16:9","seed":7}' \
  --prompt "…"

# image to video — open on a still, ten seconds, silent
studio run --model wan-3.0-openrouter --project <project> \
  --start-run <project>/latest#1 \
  --extra '{"duration":10,"aspect_ratio":"16:9","generate_audio":false}' \
  --prompt "…"

# what it actually cost, once closed
studio runs show <run>          # cost.amount is OpenRouter's charge in USD
```

A video run returns as soon as it is submitted and closes on its own;
`--poll` waits. `studio runs show <run>` reads it back either way.

## Prompting

The same model as [`studio-media-wan-3-0-t2v`](../studio-media-wan-3-0-t2v/SKILL.md),
so the same prompt: one sentence of subject, one of action, one of camera,
one of light, one of what is heard. Two differences. Prompt expansion
cannot be switched here and what the model actually saw does not come back
on the response, so a surprising result is iterated on by wording and seed
alone. And there is no `adaptive` ratio, so a clip opened on a still names
the still's ratio in `aspect_ratio` or is recomposed into `16:9`.

## What Alibaba's output checker refuses

Moderation here runs **after** the render, on Alibaba's side: a kiss between
two adults is accepted at submit, rendered, and then fails with

```
Green net check failed for image (output): Output data may contain inappropriate content.
```

Nothing is billed. fal's entry for the same model refuses the same clip at
submit instead (`422`), and Kling renders it — the map is on
[`studio-media-scene`](../studio-media-scene/SKILL.md#what-each-engine-will-actually-render--contact-between-two-people).
And with no end frame on this route, the only pin on a beat is the first
frame: what it hides, the model invents (a seated man's hidden shorts became
jeans when he stood, twice on Wan 3.0), so a seed here must show the
wardrobe that has to survive.

## What it is for, and what it is not

**For:** the shots [`studio-media-wan-3-0-t2v`](../studio-media-wan-3-0-t2v/SKILL.md)
and a start-frame-only [`studio-media-wan-3-0-i2v`](../studio-media-wan-3-0-i2v/SKILL.md)
would take, when the price matters; and for finding out what the
discount is worth — submit the same prompt here and on fal, read
`cost.amount` off this one and fal's dashboard for the other.

**Not for an end frame, references, or a negative prompt.** Those are
fal's: [`studio-media-wan-3-0-i2v`](../studio-media-wan-3-0-i2v/SKILL.md)
lands on a chosen last frame, [`studio-media-wan-3-0-r2v`](../studio-media-wan-3-0-r2v/SKILL.md)
holds a character from references. A character clip from a still that
already holds the likeness works here as it does on fal's i2v.
