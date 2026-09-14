---
name: studio-media-flux-2-pro
description: Render and edit still images with Black Forest Labs' FLUX.2 [pro] (black-forest-labs/flux-2-pro) on Replicate as a recorded run. Use when a frame is an EDIT of existing images described in words — "replace the background with the beach in image 3" — with up to 8 input images addressed by index, when a frame needs legible typography or photoreal product/architecture detail at a per-megapixel price, when the output must be an exact pixel size (`custom` + width/height), or when a draw must be repeatable with a seed. Takes no negative prompt and has no transparent background. For a character frame the default is still studio-media-gpt-image-2.
---

# studio-media-flux-2-pro

`black-forest-labs/flux-2-pro` — BFL's production FLUX.2 endpoint, a generator
and an **editor** in one model. What it sells: natural-language edits over up
to **8 input images that the prompt addresses by number**, reliable **text
rendering** (typography, infographics, UI mockups), photorealism for product
and architectural work, and hex codes honoured in the prompt for exact colour.
It bills **per megapixel** — input and output both count — so the price is
decided by `resolution` and by how much you hand it, not by a quality tier.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model flux-2-pro …`,
> and `studio models show flux-2-pro` for the live schema. This page covers
> only what is specific to this model.

## What is specific to this model

| | |
|---|---|
| Images field | `input_images`, **≤8**; the README calls them *input* images because the prompt can edit them, not only draw from them |
| Accepts | `.jpg .jpeg .png .webp .gif` — the schema names all four formats; **total input ≤9 megapixels** across the set |
| Output | one image; **`webp` default**, `jpg`, `png`; `output_quality` 0–100 (default 80) for the lossy two |
| Resolution | `resolution`: `0.5 MP` / **`1 MP` default** / `2 MP` / `4 MP` / `match_input_image` — docs recommend ≤2 MP; hard cap 2048 px per side, so `4 MP` only reaches 4 MP at `1:1` |
| Aspect | `1:1` (default) `16:9` `3:2` `2:3` `4:5` `5:4` `9:16` `3:4` `4:3`, `match_input_image`, and **`custom`** — then `width`/`height` 256–2048 in multiples of 16 replace `resolution` |
| Seed | `seed` — an integer, repeatable |
| Safety | `safety_tolerance` 1 (strictest) – 5 (most permissive), default 2 |
| Price | $0.015 per run **+** $0.015 per input megapixel **+** $0.015 per output megapixel (docs, September 2026). No refs at `1 MP` ≈ $0.03; `2 MP` ≈ $0.045; `4 MP` ≈ $0.075; add ≈ $0.015 per megapixel of references sent |
| Not here | **no negative prompt**, no transparent background, no quality tier, no `input_fidelity` |

## Invoke

```bash
# a plate, repeatable
studio run --model flux-2-pro --project <project> \
  --no-refs --aspect-ratio 3:2 \
  --extra '{"resolution":"2 MP","seed":7,"output_format":"png"}' \
  --prompt "…"

# an edit of a finished frame — --image-run is always image 1
studio run --model flux-2-pro --project <project> \
  --image-run <project>/latest#1 \
  --aspect-ratio match_input_image \
  --extra '{"resolution":"match_input_image","output_format":"png"}' \
  --prompt "Replace the sky in image 1 with an overcast dawn; keep everything else"
```

## Editing — the input images are numbered, and the prompt says so

Every image bound lands in `input_images` in a fixed order — `--image-run`
first, then `--character`, `--ref-run`, `--input`, `--key` — and the model
reads them as **image 1, image 2, …**. That index is the editing language: *"put the jacket from image 2 on the
man in image 1"*, *"replace the background with the beach in image 3"*. A
prompt that never names an index still uses the set — the docs say the model
draws style, composition and elements from all of them — but an **edit** that
must keep most of a frame should name the frame it edits and say what stays.
Bind the frame being edited with `--image-run` so it is image 1;
`match_input_image` on both `aspect_ratio` and `resolution` follows the
**first** image only.

The set is capped two ways: **8 images**, and **9 megapixels in total**. A
2K frame is ~4 MP, so three of them already overflow the budget and Replicate
refuses the request. Send a downsized reference, or fewer of them; the
identity library's tagged subsets (`--pick-tag face`) are the usual way to a
small set.

## Resolution vs. `custom` — two ways to size, never both

- `resolution` picks a megapixel budget and the aspect ratio shapes it. It is
  what a still that will be animated wants: `2 MP` at `16:9` is ~1920×1080.
- `aspect_ratio: custom` with `width` and `height` sets the frame exactly;
  `resolution` is then ignored. Values are rounded to a multiple of 16
  silently — pass ones that already are, so the recorded `input` is what
  rendered.

`4 MP` exists and the docs recommend against it; the 2048-px side cap means
anything but `1:1` cannot reach 4 MP anyway. For a bigger still, render at
`2 MP` and enlarge with [`image-upscale`](../studio-media-image-upscale/SKILL.md).

## No negative prompt — and a "no" in the prompt is worse than nothing

Nothing here takes a negative prompt, and the README is explicit that a
negated phrase (*"no text"*, *"no extra fingers"*) can add the thing it names.
Describe what should be there instead: *"clean background, hands resting out
of frame"*. The same applies to an edit — say what the region becomes, not
what it stops being. For a model with a real `negative_prompt` field, only
[`veo-3.1`](../studio-media-veo-3-1/SKILL.md) has one, and it is a video engine.

## Prompt shape — priority order, or JSON

The docs ask for subject first, then action, style, context, and say a
structured JSON prompt is read natively: `scene`, `subjects`, `style`,
`lighting`, `camera` (angle, distance, focal length, aperture, ISO) and
`color_palette` (hex codes or names), each in plain English. A JSON prompt is
just a string to the runner — pass it with `--prompt` as usual; nothing here
validates its fields. Hex codes in a prose prompt are honoured too, which is
the lever for brand colour.

## Choosing between it and the others

- **A character frame** — [`gpt-image-2`](../studio-media-gpt-image-2/SKILL.md)
  is still the default. This model's docs claim character consistency across
  a reference set, and `--character` binds into `input_images` as elsewhere,
  but nothing about it is held at high fidelity automatically and the
  9-megapixel budget is small for a face pool. Try it for a character when the
  frame is chiefly an *edit* of an approved still.
- **Change one thing in an existing frame** — this model or
  [`gpt-image-2.5-sunburst`](../studio-media-gpt-image-2-5-sunburst/SKILL.md).
  Sunburst is tuned for the edit being exact; this one is cheaper at 1–2 MP
  and can address several source images by index in one instruction.
- **Legible text, or 4K** — [`nano-banana-pro`](../studio-media-nano-banana-pro/SKILL.md)
  for 4K; this model renders text well but tops out at 2048 px a side.
- **A photoreal plate with nobody in it** — this model or
  [`krea-2-large`](../studio-media-krea-2-large/SKILL.md). Krea transfers a
  *look* from style images and has a `creativity` dial; this one takes a
  literal size and edits what it is given. Both have a seed.
- **An exact pixel size** — this model (`custom`), or
  [`gpt-image-2`](../studio-media-gpt-image-2/SKILL.md)'s explicit sizes.
- **A transparent PNG** — [`gpt-image-1.5`](../studio-media-gpt-image-1-5/SKILL.md).
  There is no background control here.

`black-forest-labs/flux-2-max`, `flux-2-flex` and the open-weight `flux-2-dev`
are separate Replicate models with their own prices and are not registered.

## Handing a frame onward

Default output is **`.webp`**, which Kling rejects. Ask for `png` at
generation time (`--extra '{"output_format":"png"}'`), or convert the run's
output — the source is never modified:

```bash
studio runs outputs <project>/latest
studio convert --run <project>/latest#1 --for kling --add-input <project>
```

## When the output goes wrong

- **The edit rewrote the whole frame.** The prompt did not say what stays.
  Name the image by index, name the region, and add *"keep everything else"*;
  bind the edited frame with `--image-run` and use `match_input_image`.
- **The wrong image was edited.** Index order is binding order — check the
  recorded `input` for which URL was `input_images[0]`.
- **Refused at submit for input size.** The set is over 9 MP. Fewer or
  smaller references.
- **The thing you excluded appeared.** A negated phrase in the prompt.
  Rewrite it as what should be there.
- **Smaller than asked.** `4 MP` at a non-square ratio hit the 2048 px side
  cap, or `custom` was set and `resolution` ignored.
- **The frame is the wrong shape.** `match_input_image` followed the first
  reference, or `custom` was set without `width`/`height` — pass an explicit
  ratio.
- **Not the same image twice.** No `seed` was set, or the payload differs by
  one field — diff the two runs' recorded `input`.
