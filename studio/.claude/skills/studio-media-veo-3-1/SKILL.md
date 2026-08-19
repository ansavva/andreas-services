---
name: studio-media-veo-3-1
description: Generate videos with synced audio on Google Veo 3.1 via google/veo-3.1 on Replicate. Reach for it over Kling or Seedance when a shot needs a repeatable seed or a real negative_prompt parameter — it is the only engine here with either. Covers the reference-image trap (refs only work at 16:9 and 8 seconds), start/end frame interpolation, the 4/6/8s duration enum, and the fast/lite tiers.
---

# studio-media-veo-3-1 — Google Veo 3.1

The control-oriented engine of the `studio-*` family. Reach for it when a shot
needs to be **reproducible** or when negative direction has to be a real
parameter rather than a phrase folded into the prompt — Veo is the only
registered video model that offers either.

Rendered with **`google/veo-3.1` on Replicate**, 24 fps, native synced audio,
SynthID-watermarked.

Choosing between the video engines:

| | Veo 3.1 | `studio-media-kling` | `studio-media-seedance` |
|---|---|---|---|
| Reference images | 3 — **only at 16:9 + 8s** | 7 (start frame counts) | 9 |
| First / last frame | both | both | both |
| **Seed** | **yes** | no | no |
| **`negative_prompt` param** | **yes** | no | no |
| Native multi-shot | no | 6 cuts | no |
| Duration | 4 / 6 / 8 s | 3–15 s | range + intelligent |

Kling still wins for multi-shot and for a large reference set at any ratio.
Seedance still wins on reference count. Veo wins when you need to render the
same thing twice.

## A likeness is a likeness

A character built from photographs of a real person is a real person's likeness.
Settle consent before anything is published.

## The model

`google/veo-3.1` — <https://replicate.com/google/veo-3.1>

| Input | Notes |
|---|---|
| `prompt` | Required. No documented character ceiling. |
| `duration` | Enum **`4` / `6` / `8`**, default `8`. Not a range — `5` is rejected. |
| `resolution` | `720p` · `1080p`, default `1080p`. |
| `aspect_ratio` | `16:9` · `9:16`, default `16:9`. Only two. |
| `image` | First frame. |
| `last_frame` | Ending frame — interpolates between the two. **Ignored when `reference_images` is set.** |
| `reference_images` | **1–3** images for subject consistency. See the trap below. |
| `negative_prompt` | A real parameter. Keep negative direction OUT of the prompt text. |
| `seed` | Omit for random. **The only reproducibility lever in the registry.** |
| `generate_audio` | Default `true`. |

### The reference-image trap

**`reference_images` only works at `aspect_ratio: "16:9"` and `duration: 8`.**

Nothing enforces this. Every other combination is schema-valid, validates
locally, submits, bills, and comes back with the reference set silently ignored —
so a 9:16 render with three references of `<name>` is a full-price generation
that never saw them. This is the single most expensive mistake available on this
model.

Two consequences worth holding:

- **Portrait work cannot use references here.** For a 9:16 shot that has to hold
  `<name>` on-model, use Kling or Seedance instead.
- **A `last_frame` is dropped the moment references are present.** You get
  reference-guided generation *or* frame-to-frame interpolation, never both. Kling
  has the same either/or with its end frame, and for the same reason: pick which
  constraint matters more for the shot.

Both facts sit in the `reference_images` field description rather than anywhere
structural, which is why they are restated here.

## `denied` values

None. The schema and README do not contradict each other on any single value —
the reference-image constraint above is conditional rather than a banned value,
so it lives in the registry `note` instead of a `denied` block.

**Unverified:** `accepts_ext`. The README names no accepted image formats, so the
registry's `.jpg/.jpeg/.png/.webp` is the onboarding default carried over.
Confirm before trusting a `.webp` binding.

## Invoke

`studio prompt`'s `--engine` list does not include this model, so drive it
directly and pass its parameters with `--extra`:

```bash
set -a; . ./.env; set +a          # REPLICATE_API_TOKEN

studio run \
  --model veo-3.1 --project <project> \
  --prompt "…" \
  --extra '{"duration": 8, "resolution": "1080p", "aspect_ratio": "16:9",
            "negative_prompt": "on-screen text, watermarks", "seed": 42}' \
  --slug <slug> --poll
```

Bind images with `--start-run` / `--start-key` (→ `image`), `--end-run` /
`--end-key` (→ `last_frame`), and `--ref-run` / `--key` (→ `reference_images`).

**Negative direction goes in `--extra` as `negative_prompt`, not in the prompt
text.** This is the opposite of Kling and Seedance, where an `avoid` clause in the
prompt is the only option. Doing it the Kling way here wastes prompt tokens on
something the model has a dedicated field for.

**Show the user the exact prompt and get approval before submitting** — every run
bills. `--dry-run` renders the payload without spending.

### Holding a seed

With a seed fixed, the same prompt and parameters reproduce the same clip. That
makes the iterate-one-thing-at-a-time loop actually work: change the lighting
line, hold everything else, and the difference you see is the change you made.
On Kling that is impossible, which is why its page leans so hard on locking the
prompt byte-for-byte. Here, lock the seed instead and the discipline gets much
cheaper.

### Output — the run owns it

Every submission is a run under
`projects/<project>/runs/<YYYY-MM-DD_HH-MM-SS>_<slug>/`, holding `request.json`
(inputs as S3 **keys**), `result.json`, and `output/` with the video. `--poll`
archives it automatically. Replicate output URLs are not permanent.

**S3 is the only origin: assets are never uploaded to Replicate**, only presigned
from the bucket at submit time. Inspect runs with `studio runs`.

## Formats and caps

| | |
|---|---|
| Duration | **4, 6 or 8 s** — nothing between |
| Aspect ratio | **16:9 · 9:16 only** — no 1:1, no 21:9 |
| Resolution | 720p · 1080p, 24 fps |
| Reference images | 1–3, **16:9 + 8s only** |
| Frames | first + last, but last is dropped when refs are present |
| Prompt | no documented ceiling |

Only two aspect ratios is the narrowest of the three engines — Kling adds 1:1,
and a still cropped for a square or 21:9 target has nowhere to go here.

## Cheaper tiers

`google/veo-3.1-fast` and `google/veo-3.1-lite` exist on Replicate and are **not
registered**. Fast is the more used of the whole family, which suggests iterating
there and finishing on the base model — the same standard/pro discipline
`studio-media-kling` describes. Onboard one with `studio add-model` if that
pattern is wanted; check its schema matches this one first, because the entry
here should not simply be copied.

## Failure modes

The README is written as capability marketing and states very few limitations, so
this section is thinner than Kling's by necessity. What is documented or follows
from the schema:

- **A silently ignored reference set** — the trap above. By far the most likely
  way to waste money here.
- **Rejected duration.** `5` and `7` look reasonable and are not in the enum.
- **Re-describing a start frame.** The README's own image-to-video guidance says
  the prompt should describe the motion wanted, not restate what the image
  already shows — the same drift failure Kling has.
- **Incompatible start/end pair.** The README asks that the two frames be
  visually compatible and the transition physically plausible; an implausible
  pair is where interpolation breaks down.
- **SynthID watermarking** is applied to every output and is not optional.

## Verified

`studio run --model veo-3.1 --dry-run` with
`--extra '{"duration": 8, "resolution": "1080p", "aspect_ratio": "16:9",
"negative_prompt": "…", "seed": 42}'` emits a correct payload — every field
passes through to the Replicate `input` unchanged and the endpoint resolves to
`google/veo-3.1`. This is also the first registry entry to use the
`negative`-as-parameter path, and it routes correctly.

**No paid render has been made on this model here.** Every behavioural claim above
comes from the live schema or the README. The first real run should test the
reference-image trap directly — three references at 16:9 + 8s, then the same
three at 9:16 — and the finding belongs in this section.
