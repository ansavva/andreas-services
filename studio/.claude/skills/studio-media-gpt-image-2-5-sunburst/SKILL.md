---
name: studio-media-gpt-image-2-5-sunburst
description: Render and edit still images with OpenAI's GPT Image 2.5 Sunburst (openai/gpt-image-2.5-sunburst) on Replicate as a recorded run. OpenAI's newest image model, tuned for EDITING PRECISION — change one named thing in an image and keep identity, composition and lighting untouched — with two quality tiers above gpt-image-2's (`xhigh`, `max`) for final assets, and a transparent background its docs endorse. Priced per quality tier and `auto` bills at the xhigh rate, so the registry defaults quality to medium. For a fresh character frame the default is still studio-media-gpt-image-2.
---

# studio-media-gpt-image-2-5-sunburst

`openai/gpt-image-2.5-sunburst` — OpenAI's newest and most capable image
model, and one of two GPT Image 2.5 entries here — the other,
[`gpt-image-2.5-flare`](../studio-media-gpt-image-2-5-flare/SKILL.md), has
the same inputs and prices and is tuned for speed. Sunburst's docs lead with
**editing**:
targeted changes that leave the rest of the image alone, style transfer,
compositing a person into a new scene while preserving their likeness. It
takes the same inputs as [`gpt-image-2`](../studio-media-gpt-image-2/SKILL.md)
and adds two quality tiers above `high`. No OpenAI key needed; it bills
through Replicate.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model gpt-image-2.5-sunburst …`,
> and `studio models show gpt-image-2.5-sunburst` for the live schema. This
> page covers only what is specific to this model.

## What is specific to this model

| | |
|---|---|
| Images field | `input_images`, no documented cap |
| Accepts | `.jpg .jpeg .png .webp` — the README names no formats; this is the common set |
| Output | **`webp` default**, `png`, `jpeg` — `jpeg`, not Google's `jpg` |
| Aspect | ratios, `auto`, and explicit pixel sizes to `3840x2160` — the schema says sizes above 2560x1440 are experimental |
| Quality | `low` / **`medium`** (registry default) / `high` / `xhigh` / `max` / `auto` |
| Moderation | `auto` / **`low`** (registry default) |
| Background | `auto` / `transparent` / `opaque` — **transparent is endorsed here**, unlike gpt-image-2 |
| Price | per output image, by quality tier — see below |

## Quality is the price — and `auto` is not the cheap choice

The bill is decided by `quality` alone (Replicate, September 2026):

| `quality` | per image |
|---|---|
| `low` | $0.012 |
| `medium` | $0.047 |
| `high` | $0.128 |
| `xhigh` | $0.25 |
| `max` | $0.50 |
| `auto` | **$0.25** — billed at the `xhigh` rate |

The schema's default is `auto`, which is the second-most expensive tier. The
registry therefore defaults `quality` to `medium`, the same as the other GPT
Image entries; a run carries `"quality": "medium"` unless `--extra` says
otherwise. Draft on `low`, and step up to `xhigh` or `max` only for the frame
that ships — a `max` render costs forty `low` ones. Read the price off the
payload before submitting: it is one field. For a batch of drafts,
[Flare](../studio-media-gpt-image-2-5-flare/SKILL.md) costs the same per image
and returns sooner.

## Editing — say what changes, and what must not

The docs' own advice, and it matches how the frame-first workflow uses an edit:

- **Name the change.** "Change the red hat to light blue velvet", not "make it
  better".
- **Lock the rest.** "Change only the lighting; preserve the subject's face,
  pose and clothing." Without the lock the model may reinterpret more than
  asked.
- **Quote text.** Exact copy in "quotes", then describe the typography.
- **Photo language for realism.** Lens, light quality, framing.

An edit is a run with the source image as its first reference and the
instruction as its prompt:

```bash
studio run --model gpt-image-2.5-sunburst --project <project> \
  --ref-run <project>/latest#1 \
  --extra '{"quality":"low","output_format":"png"}' \
  --prompt "Change only the lighting to soft coastal daylight; preserve the face, pose and clothing."
```

**The lock cuts both ways.** Told "make the head larger, do not narrow the
shoulders", it made the head slightly larger and left the shoulders exactly
where they were — so a head-to-shoulder *ratio* barely moved, because a ratio
is two things and only one was named. An edit here changes what it is told
and freezes the rest; a relationship between two parts of the figure is not a
thing it can adjust. Regenerate instead, with the edited frame as a physique
reference and a real full-length photograph as the proportion reference — see
[`studio-media-image`](../studio-media-image/SKILL.md).

## Adding a second character to a frame

This is the model for the second link of the two-character chain in
[`studio-media-image`](../studio-media-image/SKILL.md#two-characters-in-one-frame--one-at-a-time-never-both-at-once):
the first character's finished frame goes first as the edit target, the second
character's face references follow, and the prompt says *add* a second person
in the empty space, *keep everything else exactly as it is*, and that the new
person is *the man in the remaining images, and ONLY him*. The first figure
survives pixel-for-pixel; the only face drawn is the second's. Generating both
in one run instead blends them.

```bash
studio run --model gpt-image-2.5-sunburst --project <project> \
  --image-run <project>/latest --character <name-2> --pick-tag default,face \
  --aspect-ratio 3:2 --prompt-file step2.txt
```

## Character frames — same fidelity, different default

References are held at high fidelity automatically, as on `gpt-image-2`, so a
`--character <name> --pick-tag face` frame works the same way. The default
for a **fresh** character frame stays `gpt-image-2`, because nothing in this
model's docs claims a better likeness from references — its claim is about
what it leaves alone when editing. Reach for this one when the frame already
exists and needs one thing changed, when the identity must survive a
composite into a new scene, or when `xhigh`/`max` is worth paying for.

## Transparent backgrounds — endorsed, not just listed

`gpt-image-2`'s schema lists `background: transparent` and its docs disown
it, which is why that value is `denied` there. This model's README lists
`transparent` as a supported input with no caveat, so there is no denial
here. Ask for it with `--extra '{"background":"transparent","output_format":"png"}'`
— `webp` also carries alpha, but `png` is what every downstream tool expects
of a cutout. [`gpt-image-1.5`](../studio-media-gpt-image-1-5/SKILL.md) is the
other route to a transparent PNG and the only one with an explicit
`input_fidelity` knob.

## Output format — convert before handing a frame to Kling

Writes **`.webp` by default**, and Kling accepts only `.jpg/.jpeg/.png`. Ask
for `png` at generation time, or convert an existing output (the source is
never modified):

```bash
--extra '{"output_format":"png"}'
studio convert --run <project>/latest#1 --for kling --add-input <project>
```

## When the output goes wrong

- **More changed than you asked.** The prompt named the change but not the
  lock. Add "change only …; preserve …".
- **The bill was $0.25 for a draft.** `quality` was `auto` — something set it
  in `--extra`. The registry default is `medium`; drafts want `low`.
- **Soft detail on a final.** Step `quality` up; `xhigh` and `max` exist for
  exactly this and nothing else. A seed bound for a video engine wants `high`
  at least — the clip inherits the still's softness and adds nothing back.
- **`E005` on an edit.** Moderation, not the payload. Measured 2026-09-18: it
  flags an edit that re-poses a shirtless man together with a second man
  ("eyes locked, a foot apart"), and refuses a kiss still outright. Nothing
  billed. Re-pose one figure at a time — the first alone on
  [`nano-banana-pro`](../studio-media-nano-banana-pro/SKILL.md), the second
  added here — and for a kiss still use
  [`seedream-5-pro`](../studio-media-seedream-5-pro/SKILL.md); the chain and
  the map are in
  [`studio-media-image`](../studio-media-image/SKILL.md#re-pose-one-person-per-generation).
- **A 4K size came back odd.** Sizes above 2560x1440 are experimental per the
  schema. Render at `2048x…` and enlarge with
  [`image-upscale`](../studio-media-image-upscale/SKILL.md).
- **Kling refused the frame.** It is `.webp`; see the format section above.
