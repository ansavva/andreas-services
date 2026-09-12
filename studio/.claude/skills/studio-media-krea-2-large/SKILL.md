---
name: studio-media-krea-2-large
description: Render still images with Krea 2 Large (krea/krea-2-large) on Replicate as a recorded run. Use for photorealism, natural light and textured or painterly looks with no recurring character in frame, when a LOOK should be lifted from up to 10 style images, when the prompt should be rendered literally (`creativity: raw`) or freely embellished (`high`), or when a frame must be repeatable — the only image model here with a seed. Its reference input transfers style, not identity: for a character frame use studio-media-gpt-image-2.
---

# studio-media-krea-2-large

`krea/krea-2-large` — Krea's flagship still model, the larger of the two Krea 2
variants. What it sells: **photorealism** (natural light, shallow depth of
field, real-world texture) and **expressive artistic styles**, with a
`creativity` dial that says how far it may wander from the words, and a
**style transfer** input that lifts the look of up to 10 images onto the
result. It bills a flat price per image and exposes almost no other knobs.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model krea-2-large …`,
> and `studio models show krea-2-large` for the live schema. This page covers
> only what is specific to this model.

## What is specific to this model

| | |
|---|---|
| Images field | `style_reference_images`, **≤10** — a **style** input, see below |
| Accepts | `.jpg .jpeg .png .webp` — the README names no formats; this is the common set, and a rejection at submit is the signal it is narrower |
| Output | one image, format not selectable — no `output_format` field |
| Resolution | not selectable — no `size`, `resolution` or `quality` field |
| Aspect | `1:1` (default) `4:3` `3:2` `16:9` `2.35:1` `4:5` `2:3` `9:16` — the only image model here with a cinema `2.35:1` |
| Creativity | `raw` / `low` / `medium` (default) / `high` |
| Seed | `seed` — an integer, repeatable; **no other image model here has one** |
| Style strength | `style_reference_strength` 0–1, default 0.5; applies to every style image at once |
| Moodboard | `moodboard_id` + `moodboard_strength` 0–1, default 0.35 — a Krea-webapp object, see below |
| Price | flat per image: $0.060; $0.065 with style references; $0.070 with a moodboard (docs, September 2026) |
| Not here | no negative prompt, no transparent background, no output format, no resolution tier, no safety knob |

## Invoke

```bash
studio run --model krea-2-large --project <project> \
  --no-refs --aspect-ratio 3:2 \
  --extra '{"creativity":"raw","seed":7}' \
  --prompt "…"
```

## Its image input is a style, not an identity

`style_reference_images` is the model's only image field, so the runner binds
the reference list to it — `--key`, `--ref-run`, `--input` and `--character`
all land there. The model then **extracts the style** of those images and
applies it to the output at `style_reference_strength`. Its docs make no claim
about subjects, faces or composition, and nothing about the field is a
likeness reference.

So `--character <name> --pick-tag face` on this model validates, bills the
style-reference price, and gives back the *look* of those photos — their
light, grain and palette — around whoever the prompt describes. It does not
hold `<name>` on-model. For a character frame the default is still
[`gpt-image-2`](../studio-media-gpt-image-2/SKILL.md); for several identity
references into one composition,
[`seedream-5-pro`](../studio-media-seedream-5-pro/SKILL.md). Reach for this
model's style input when you *want* a look transferred: a few frames from a
finished scene to match its grade, a set of paintings, a product shoot's
lighting.

Order and count still matter. The strength is one number for the whole set, so
a mixed set averages into a look nobody chose — pick two or three images that
agree with each other rather than a whole pool.

## `creativity` — the lever that replaces a negative prompt

Nothing here takes a negative prompt. What this model offers instead is how
literally it reads the positive one:

| Value | The docs' wording | Reach for it when |
|---|---|---|
| `raw` | renders only what you describe | a storyboard panel that must match its brief; anything a later step depends on |
| `low` | fills in obvious gaps | a described scene with no strong opinion about the rest |
| `medium` | adds reasonable interpretation | the default; a loose brief |
| `high` | takes meaningful creative liberty | exploring, a mood, a poster with room to surprise |

A frame that will be handed to a video engine wants `raw` or `low`: the
motion prompt is written against what is in the frame, and liberty taken here
is a mismatch there.

## Seed — repeatable, and unique among the image models

`seed` is a plain integer with no range. Set it and the same payload renders
the same image, which makes this the one still model where a prompt can be
iterated one word at a time against a fixed draw. Leave it unset for variety.
The seed is part of the recorded `input`, so a run's JSON is enough to
reproduce it.

## Moodboards — an external object, not an S3 one

`moodboard_id` names a moodboard built in the Krea webapp
(`https://www.krea.ai/moodboards`, the UUID from its `?share=<uuid>` link). It
is a bigger, curated set of style images that lives at Krea, so hard rule #3
does not reach it — nothing is uploaded from here, and nothing here can create
or inspect one. Pass it with `--extra '{"moodboard_id":"<uuid>"}'` and tune
`moodboard_strength`. It combines with `style_reference_images`. There is no
moodboard in any studio library; if a brief needs one, it is made by hand at
Krea first.

## Choosing between it and the others

- **A character frame** — [`gpt-image-2`](../studio-media-gpt-image-2/SKILL.md).
  This model has no identity input at all.
- **Legible text, or 4K** — [`nano-banana-pro`](../studio-media-nano-banana-pro/SKILL.md).
  This model makes no text claim and offers no resolution choice; a still that
  needs to be bigger goes through
  [`image-upscale`](../studio-media-image-upscale/SKILL.md) afterwards.
- **A photoreal or painterly plate with nobody recurring in it** — this model.
  Establishing shots, backgrounds, textures, posters, a look to match a scene to.
- **The same frame again, changed one word** — this model, with a `seed`.
- **A transparent PNG** — [`gpt-image-1.5`](../studio-media-gpt-image-1-5/SKILL.md).

`krea/krea-2-medium` is the faster, cheaper sibling the README recommends for
illustration, anime and painting. It is a separate model and is not registered
here.

## Handing a frame onward

The output's format is the model's choice, not yours. Check the run's outputs
before binding one as a start frame — Kling rejects `.webp` — and convert if
needed; the source is never modified:

```bash
studio runs outputs <project>/latest
studio convert --run <project>/latest#1 --for kling --add-input <project>
```

## When the output goes wrong

- **The subject is right and the face is wrong.** Expected: the image input is
  a style, not a likeness. Render the frame on `gpt-image-2` instead.
- **The style did not take.** `style_reference_strength` is 0.5 by default;
  raise it towards 1, and cut the set to images that share the look.
- **The style took over the content.** Lower the strength, or drop the
  reference set and describe the look in words.
- **Extra things in the frame you never asked for.** `creativity` is
  `medium`; drop to `raw`.
- **Too literal, flat, under-lit.** The prompt is being rendered as written on
  `raw`; describe the light and lens explicitly, or move to `low`.
- **Not the same image twice.** No `seed` was set, or the payload differs by
  one field — diff the two runs' recorded `input`.
