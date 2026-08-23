---
name: studio-media-kling
description: Generate videos with Kling 3.0 / O3 Omni via kwaivgi/kling-v3-omni-video on Replicate (pay-per-second, reference_images for character consistency, native multi-shot). Use whenever a video is rendered on Kling rather than Seedance. Covers the model schema, native multi-shot up to 6 cuts, start/end frames, image-to-video prompting, cross-clip consistency, and chaining into a scene. Pair with studio-media-prompt (--engine kling-replicate) and studio-media-character.
---

# studio-media-kling — Kling 3.0 / O3 Omni

The Kling rendering engine of the `studio-*` family. Kling is the counterpart to
`studio-media-seedance`: reach for it when you want native multi-shot, when a subject
needs more than ~3 beats, or when a draft renders better here than there.

Rendered with **`kwaivgi/kling-v3-omni-video` on Replicate** (`--engine
kling-replicate`), which reuses the Replicate token, upload helper and S3 flow
`studio-media-seedance` already has.

> Kling's own API (`api-singapore.klingai.com`) hosts the same models but bills
> against prepaid resource packages rather than per second, so it is not used
> here. A working client for it was removed in favour of Replicate; recover it
> from git history if a package is ever purchased.

The family:
- **`studio-media-prompt`** — authors the prompt. `--engine kling-replicate` compiles a
  `shots` timeline into the model's `multi_prompt` array and emits a ready
  Replicate `input`.
- **`studio-media-character`** — `reference_images` here behaves like Seedance's, so a
  character's existing S3 reference set carries over. `studio character textblock`
  gives a pasteable identity anchor when driving from a start frame instead.
- **`studio-media-seedance`** — the other model family, with its own schema.

## A likeness is a likeness

A character built from photographs of a real person is a real person's likeness.
Settle consent before anything is published.

## The model

`kwaivgi/kling-v3-omni-video` — <https://replicate.com/kwaivgi/kling-v3-omni-video>

| Input | Notes |
|---|---|
| `prompt` | **max 2500 chars.** Supports `<<<image_1>>>` template refs. |
| `start_image` | First frame. `.jpg/.jpeg/.png`, **max 10 MB**, min 300px, aspect 1:2.5–2.5:1. |
| `end_image` | Last frame; requires `start_image`. |
| `reference_images` | The character-consistency mechanism. **The cap of 7 counts the start frame too** — see below. 4 with a reference video. |
| `reference_video` | 3–10s; `video_reference_type` `feature` (style/camera) or `base` (editing). |
| `multi_prompt` | JSON-encoded array `[{"prompt": "...", "duration": N}]`. **Max 6 shots, durations must sum to `duration`.** |
| `mode` | `standard` = 720p · `pro` = 1080p · `4k`. |
| `aspect_ratio` | `16:9` · `9:16` · `1:1`. **Required only when there is no start frame.** |
| `duration` | 3–15 seconds. |
| `generate_audio` | Default false. Mutually exclusive with a reference video. |

**No `seed` and no `negative_prompt`.** Negative direction goes in the prompt
text; `--engine kling-replicate` folds it in. With no seed, holding the prompt
byte-identical is the only reproducibility lever — see the locked template below.

### Cost

| Mode | No audio | With audio |
|---|---|---|
| standard (720p) | **$0.168/s** | $0.224/s |
| pro (1080p) | $0.224/s | $0.28/s |
| 4k | $0.42/s | $0.42/s |

A 9s standard clip is ~$1.52. Iterate at `standard`, finish at `pro`.

## Hard constraints

| | |
|---|---|
| Duration | 3–15 s |
| Multi-shot | **6 cuts max**, ≥1 s each, summing to the total |
| Aspect ratio | 16:9 · 9:16 · 1:1 (ignored when a start frame is supplied) |
| Images | `.jpg/.jpeg/.png` only — **`.webp` is rejected**, so convert S3 references |
| Image COUNT | **7 in total**, start frame included — so 6 references at most alongside one |
| Start **and** end frame | **2 images TOTAL** — `reference_images` must be empty. See below |
| Prompt | 2500 chars |

`studio prompt --engine kling-replicate` enforces these as hard errors at
author time rather than after a spent generation.

### The image cap counts the start frame

`reference_images` takes up to 7, and a start frame may be combined with them —
which reads as 7 + 1 and is not. The limit is **seven images in total**, so a
start frame leaves room for six references. Exceeding it fails the prediction
outright:

```
Error code 1201: The number of images and elements exceeds the limit, max number is 7.
```

It fails fast and cheap, but only after a submit, and the two facts that produce
the mistake sit in different rows of the schema table above. With a character
whose `default_set` holds seven — a full face turnaround plus body plates, which
is the shape `shoot` produces — binding `--character` and a start frame together
is over the line by exactly one. Narrow the selection with `--pick`; the start
frame already carries wardrobe and framing, so drop a body plate rather than a
face one.

### An end frame clears the reference list

A start frame and `reference_images` combine happily — that is the whole reason
to reach for this model over Seedance. Add an **end** frame and that stops being
true: the request is then capped at those two images and rejected outright if
anything else is present.

```
Error (E006): Cannot use reference images together with end_image when
start_image is set (max 2 images with end frame).
```

Nothing in the live schema says so, and the fields are independently valid, so
this surfaces only after a submit. It is worth knowing because bracketing a shot
between two approved compositions is otherwise the strongest thing you can do
here — the prompt then only has to describe the movement between them. Just do
not also send references: the two frames have already fixed the look at both
ends.

Enforced locally, so it costs a message rather than a round trip.

## Workflow

**No token export is needed.** `studio run` reads `REPLICATE_API_TOKEN`
from the environment and falls back to `studio/.env` on its own, so the
`set -a; . ./.env; set +a` line older notes open with is a no-op.

```bash
# 1) author + validate; emits a ready Replicate input
studio prompt shot.json \
  --engine kling-replicate

# 2) submit as a recorded run — the shared submitter serves both video engines.
#    It records the run, mints presigned URLs at submit time, polls WITHOUT
#    Prefer:wait (a timed-out wait retries internally and bills duplicates),
#    and archives the finished video into the run.
studio run \
  --model kling --project <project> --input-file input.json \
  --character <name> --name <file> --poll
```

Bind images with `--start-run` / `--end-run` (→ `start_image` / `end_image`),
`--ref-run` (→ `reference_images`), or `--key` for an explicit S3 object. Unlike
Seedance, Kling lets a start frame and `reference_images` combine. Kling accepts
only `.jpg/.jpeg/.png`, and the submitter rejects a `.webp` binding up front
rather than letting the render fail.

**Show the user the exact prompt and get approval before submitting** — every run
bills.

Parsing note: Replicate's `logs` field can contain raw control characters, so
`json.loads(..., strict=False)` when reading a prediction. Strict parsing fails.

### Output — the run owns it

Every submission is a run under `<project>/runs/<YYYY-MM-DD_HH-MM-SS>_<slug>/`,
holding `request.json` (inputs as S3 **keys**), `result.json`, and `output/` with
the video. `--poll` archives it automatically — download-then-upload, so bytes
never pass through the agent context. Replicate output URLs are not permanent.

**S3 is the only origin: assets are never uploaded to Replicate**, only presigned
from the bucket at submit time. Inspect runs with `studio runs`
(`list` / `show` / `outputs --presign`).

## Image-to-video: don't describe what the frame already shows

A start frame **already fixes** background, lighting, wardrobe and appearance.
Re-describing them makes the model fight the image and drift — the most common
image-to-video failure, and it reads as a model problem when it is a prompt
problem.

Set `"start_image": true` in the JSON and:

- **Cut `scene` and `lighting`.** The frame owns them.
- **Shrink `subject`** to an identity anchor — `"The man from the source image,
  unchanged — same face, hair, build and wardrobe"`.
- **Repoint `negative` at drift**: `changing face, changing hairstyle, changing
  build, changing background, changing wardrobe, cuts, scene changes`, plus the
  usual anatomy terms.
- **The frame sets the output shape.** `aspect_ratio` is ignored, so crop the
  frame to the ratio you want. Kling also normalises dimensions — a 1024×1024
  source came back 960×960.
- **Watch the frame edges for wide poses.** Elbows-out clips in a narrow crop.

The validator warns if `scene`/`lighting` survive or `subject` runs past ~40 words.

## Consistency across clips: lock the template, add only deltas

The largest source of multi-clip inconsistency is **workflow, not the model**.
Refining wording between generations is the natural impulse and it is the bug:
each reworded prompt is a slightly different creative direction, so every clip is
self-consistent but inconsistent with its neighbours.

**Write each character and environment once, reuse it byte-for-byte.** Per-clip
variation must be **additive on top of** the locked base, never substituted into
it. Freeze `subject`, `scene`, `style`, `lighting`; let only `shots` change. With
no seed available anywhere on Kling, this is the *only* reproducibility lever.

### Chaining beyond one generation

Full workflow — the loop, the continuity rules, the per-part verification gate
and assembly — lives in **[`studio-media-scene`](../studio-media-scene/SKILL.md)**. In short:

1. Render part 1.
2. Export its **last frame** with `studio frames last <runref> --add-input`;
   use the resulting input-pool key as part 2's `start_image`.
3. Carry a **pose-continuity line** in part 2's `subject` — `"…, arms already
   raised in a bicep flex"` — so the pose doesn't reset on frame one.
4. Hold the locked base identical.
5. **Colour-match in assembly**; a hard cut amplifies small differences.

Assemble with `studio scenes assemble`. Parts chained this way inherit their
geometry from each other, so the stitch is a stream copy with no re-encode.

**Binding the frame: `--start-key`, not `--key`.** `--key` adds an explicit S3
object to `reference_images`; the first/last frame flags are `--start-key` /
`--start-run` (and `--end-key` / `--end-run`). Passing a start frame via `--key`
silently produces a reference-image render instead — it validates and bills.

### Shorter clips drift less

Drift accumulates within a generation; faces and hands go first. If a clip falls
apart in its back half, cut beats or duration rather than rewording.

> In tension with the 6-cut ceiling: a 15 s six-cut run may drift more than three
> chained 5 s runs. Untested for *drift* — but see below: for a **continuous**
> piece the question does not arise, because `multi_prompt` beats are cuts.

### `multi_prompt` beats are CUTS — and they are the only timing control

Two verified facts that pull against each other, and the choice between them
should be put to the user before spending:

- **Every `multi_prompt` beat is a hard cut** — framing and often camera angle
  change at each boundary. Asking for "one continuous take" while passing
  `multi_prompt` cannot work; the field is the cause, so remove it rather than
  fighting it with wording.
- **`multi_prompt` is also the only way to control *when* things happen.** Each
  beat carries an explicit `duration`. Drop it and the model allocates the
  seconds itself: long or fiddly actions get compressed, and a beat you wanted
  held gets rushed. Phrases like `"within the first second or two"` and `"for the
  whole rest of the shot"` recover some of it, unreliably.

Getting both means **chaining** — one continuous take per part, cut where you
chose. See [`studio-media-scene`](../studio-media-scene/SKILL.md).

### Favour slow, deliberate motion

Kling is markedly more consistent on slow controlled movement than on fast action
or complex environmental interaction. When a shot keeps breaking, ask whether a
slower version conveys the same idea.

Worth testing (community-sourced, unverified): an explicit `"background geometry
stays locked while the subject moves"` line, and giving the motion a concrete
secondary anchor (water rippling, fabric shifting).

**Don't rely on the model for on-screen text** — lettering is re-mangled between
runs. Add it in post.

## Legacy parameters in old guides — all wrong now

Third-party Kling guides are overwhelmingly written against API 1.x:

| Claimed | Reality |
|---|---|
| JWT signed from AccessKey + SecretKey | Plain `Authorization: Bearer <key>` |
| `model_name` in the body | Model is in the path / the Replicate model slug |
| `cfg_scale`, `mode: std\|pro` | Not present (Replicate's `mode` is resolution) |
| `duration: "5"\|"10"` as a string | Integer, 3–15 |
| `negative_prompt` field | Not present |
| A `seed` | Not present |

## Open question: prose vs. serialized JSON

`studio-media-prompt`'s JSON serialization is validated against **Seedance**, following
ByteDance's own guidance. It is **not** validated on Kling, where Kuaishou's
material uses prose. The structural rules (subject-and-action lead, one camera
move, concrete verbs) hold either way, and the JSON form is what makes the
locked-template discipline mechanical — so it stays the default.

Settle it when convenient: same beat, same start frame, once as serialized JSON
and once as prose, and keep whichever tracks better. Note that with `multi_prompt`
the per-shot text is already plain prose, so this only concerns the lead-in block.

## Verified runs

`kwaivgi/kling-v3-omni-video`, image-to-video from a 1024×1024 PNG, `multi_prompt`
with 3 × 3 s beats, `mode: standard`, no audio → **succeeded** in 128 s,
9.041 s of 960×960 output, $1.52. No content-policy rejection.

**A four-part chained scene**, each part driven by the previous part's last
frame, `mode: standard`, `generate_audio: true` throughout (15 s + 10 s + 10 s +
6 s → 41.2 s assembled). Findings worth keeping:

- **`start_image` + `reference_images` together works, and stays targeted.** With
  **two** people in frame and references for only **one**, the references did not
  bleed onto the second person — they kept their own face.
- **In a chained scene, those references should be the scene's own frames** — the
  image part 1 started from plus each handoff frame — not the character's curated
  `reference/` library. Those images were made in another context and pull the
  render toward it. Reach into `reference/` only when the scene introduces
  something no existing frame shows. See
  [`studio-media-scene`](../studio-media-scene/SKILL.md); `studio frames chain`
  derives the list.
- **Every shot came back 960×960 24 fps / AAC 44.1 kHz stereo**, so chained shots
  stitch as a stream copy with no re-encode.
- **Audio needs directing.** `generate_audio: true` with no `audio` block tends to
  invent music; naming the ambience, the sounds the action makes, and what to
  exclude gets a usable bed. Keep that wording identical across shots or the
  joins become audible.
- **Removing a garment duplicates it.** Mid-clip the shirt was in his hand *and*
  on his body before resolving. Compression, not wording — the fix is more
  seconds for the motion.
- **Props not named in the prompt improvise.** A lanyard in the source frame
  became an ID badge, then vanished. Name persistent props in `subject` or accept
  the drift.
- **Held stillness holds** at short duration — a 6 s "hold a look" beat stayed
  still with no invented motion, where 15 s of it would likely not have.
- **A physically contradictory pose resolves itself toward the default.** A
  direction requiring two subjects to be in close contact *and* held apart at
  arm's length came back as ordinary close contact every time, across several
  rewordings and with the contradiction named in `negative`. Settle that kind of
  geometry in a **still** first — the model is not going to hold a pose that
  fights itself.
