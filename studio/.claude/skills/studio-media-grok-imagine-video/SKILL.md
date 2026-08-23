---
name: studio-media-grok-imagine-video
description: Animate a still image into video with synced audio on xAI Grok Imagine Video via xai/grok-imagine-video on Replicate, and edit existing video clips with a prompt. Reach for it when the job is bringing one approved still to life, when a duration between the other engines' fixed steps is needed (any integer 1-15s), or when an existing clip needs changing — it is the only registered model that edits video. Not for holding a character on-model: it has no reference images.
---

# studio-media-grok-imagine-video — xAI Grok Imagine Video

The image-animator of the `studio-*` family, and the only registered model that
**edits an existing video**. Reach for it when the work starts from one approved
still, or when a clip already rendered needs a change that would otherwise mean
re-rendering it.

Rendered with **`xai/grok-imagine-video` on Replicate**, built on xAI's Aurora
model, with natively generated synchronised audio including lip-sync.

**Not the engine for a recurring character.** It has no reference-image
mechanism at all — identity holds only as far as a single first frame carries it.
For `<name>` across multiple shots use `studio-media-kling` or
`studio-media-seedance`.

Where it wins over the others:

| | Grok | others |
|---|---|---|
| Duration | **any integer 1–15 s** | fixed enums or a stepped range |
| Video editing | **yes, ≤8.7 s in** | none |
| Aspect ratios | 8, plus `auto` | 2–3 |
| Reference images | **none** | 3–9 |
| Negative direction | **ignored entirely** | honoured |

## A likeness is a likeness

A character built from photographs of a real person is a real person's likeness.
Settle consent before anything is published.

## The model

`xai/grok-imagine-video` — <https://replicate.com/xai/grok-imagine-video>

| Input | Notes |
|---|---|
| `prompt` | Required. No documented character ceiling. |
| `image` | The still to animate. `.jpg/.jpeg/.png/.webp` — **confirmed by the README**. |
| `video` | Editing mode. Max **8.7 s** in; output matches its duration, ratio and resolution. |
| `duration` | Integer **1–15**, default 5. A true range. Ignored when editing. |
| `resolution` | `720p` · `480p`. Ignored when editing. |
| `aspect_ratio` | `auto` (default) · 16:9 · 9:16 · 1:1 · 4:3 · 3:4 · 3:2 · 2:3. Ignored when editing. With an `image` and `auto`, output takes the image's native ratio. |

**No `reference_images`, no `last_frame`, no `seed`, no `negative_prompt`.**

## `denied` values

No per-value denials — but one blanket behaviour that matters more than a denial
would:

**Negative direction is ignored.** The model has no `negative_prompt` field, and
the README is explicit that prompt-embedded negatives are dropped too: *"Negative
prompts don't work. The model ignores them."* Writing `avoid: extra fingers,
blurry` into the prompt here is not a weaker version of what Kling does — it is
dead text.

The registry records `negative: "prompt"` because that is the only fallback the
harness offers, **not** because folding it into the prompt works. Describe what
you want instead. That is the single largest difference in how this model is
driven versus the other two.

## Invoke

`studio prompt`'s `--engine` list does not include this model, so drive it
directly and pass its parameters with `--extra`:

**No token export is needed.** `studio run` reads `REPLICATE_API_TOKEN`
from the environment and falls back to `studio/.env` on its own, so the
`set -a; . ./.env; set +a` line older notes open with is a no-op.

```bash
# animate a still
studio run \
  --model grok-imagine-video --project <project> \
  --prompt "the subject slowly turns to camera and smiles, gentle push-in" \
  --start-run <runref> \
  --extra '{"duration": 8, "resolution": "720p", "aspect_ratio": "auto"}' \
  --name <file> --poll
```

Bind the still with `--start-run` / `--start-key` (→ `image`). `--ref-run` and
`--key` have nowhere to bind — there is no reference field.

**Show the user the exact prompt and get approval before submitting** — every run
bills. `--dry-run` renders the payload without spending.

### Editing an existing clip

The `video` input takes a clip and changes it from a prompt, preserving
everything not mentioned. Nothing else in the registry does this, so the
alternative is always a full re-render.

**There is no binding flag for it.** `--start-run`, `--ref-run` and friends map
onto the registry's first-frame / last-frame / reference fields; `video` is none
of those, so nothing binds a stored object to it. Editing therefore takes two
steps — and note `presign` needs `--key` for an exact object: a bare positional
is a *basename*, meaningful only alongside `--folder`.

```bash
studio presign --key <path>       # temporary HTTPS URL for that exact object
studio run --model grok-imagine-video --project <project> \
  --prompt "Add a silver necklace to the woman." \
  --extra '{"video": "<the presigned URL>"}' \
  --name <file> --poll
```

That still satisfies S3-only origin — the clip originates in the bucket and
reaches the model as a short-lived presigned URL, which is the rule. But note
what it costs: `--extra` is merged into the payload verbatim, so the clip is
**not** recorded in `request.json` as an S3 key the way a bound image is. The run
will not tell you which object it edited. Until a binding flag exists, note the
source key in the slug or keep the pairing yourself.

Output inherits the input's duration, ratio and resolution, so `duration`,
`resolution` and `aspect_ratio` are all ignored in this mode.

Per the README, describe the delta: *"Add a silver necklace to the woman"*,
*"Remove the bee from the scene"*, *"Restyle this as cyberpunk anime"*, *"Change
the setting to autumn"*.

### Output — the run owns it

Every submission is a run under
`<project>/runs/<YYYY-MM-DD_HH-MM-SS>_<slug>/`, holding `request.json`
(inputs as S3 **keys**), `result.json`, and `output/` with the video. `--poll`
archives it automatically. Replicate output URLs are not permanent.

**S3 is the only origin: assets are never uploaded to Replicate**, only presigned
from the bucket at submit time. Inspect runs with `studio runs`.

## Formats and caps

| | |
|---|---|
| Duration | **1–15 s, any integer** — the only engine here without fixed steps |
| Resolution | 480p · 720p — **no 1080p** |
| Aspect ratio | 8 ratios plus `auto`, the widest choice here |
| Images | `.jpg/.jpeg/.png/.webp`, confirmed |
| Editing input | ≤ 8.7 s |
| Reference images | none supported |

720p is the ceiling — for a finishing render at 1080p use
`studio-media-veo-3-1` or Kling's `pro` mode.

## Prompting — it differs from the other engines

The README carries an unusually specific prompt guide. What actually differs from
how Kling and Seedance are driven:

- **Structure as Subject + Action + Setting + Camera + Lighting/Mood**, written as
  natural sentences. Tag stacking (`"knight, castle, epic, 8K"`) is called out as
  a mistake.
- **Intensity modifiers matter.** Without them the model picks its own, usually
  more subtle than intended: `"car passing"` → `"car racing past at high speed"`.
- **An `AUDIO:` block at the end of the prompt** is the documented way to direct
  sound: ambience, the sounds the action makes, and short dialogue in quotes.
- **`camera switch` / `cut to` gives multi-beat sequences** in the prompt text.
  Unlike Kling's `multi_prompt`, nothing enforces the timings — there is no
  parameter behind it.
- **Animating a still: describe motion, not the image.** Same rule as everywhere,
  but it bites harder here because there is no reference set to fall back on.

## Failure modes

Documented in the README, **not** confirmed by runs of ours:

- **Negative direction silently does nothing** — the trap above.
- **15 s clips are more artifact-prone.** The README puts the sweet spot at 5–8 s.
- **Contradicting the source image** (prompting a woman over a photo of a man)
  produces incoherent output rather than an error.
- **Too many simultaneous actions** degrades it — one subject, one action, one
  camera move.
- **No camera direction given** leaves the framing to the model.

## Verified

`studio run --model grok-imagine-video --dry-run` with
`--extra '{"duration": 8, "resolution": "720p", "aspect_ratio": "16:9"}'` emits a
correct payload — fields pass through to the Replicate `input` unchanged and the
endpoint resolves to `xai/grok-imagine-video`.

**No paid render has been made on this model here.** Every behavioural claim above
comes from the live schema or the README. The first real run should be an
image-to-video from an approved still at `auto`, and the second should exercise
the editing mode, since that is the capability nothing else here has. Findings
belong in this section.
