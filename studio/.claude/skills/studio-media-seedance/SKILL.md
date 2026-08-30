---
name: studio-media-seedance
description: Generate videos with ByteDance Seedance 2.0 via `studio run --model seedance` — the multimodal engine of the studio-* family, with native audio, first/last-frame images, and reference images, videos and audio. Use whenever the user wants to create, generate, or render a video, clip, animation, or motion piece on Seedance. Covers the model input schema, the mutually exclusive image fields, the duration and resolution ranges, and how references reach Replicate (presigned URLs the runner mints at submit time). Pair with studio-media-prompt (--engine seedance) to author the prompt and studio-media-character for on-model character videos. For renders on the Kling models use studio-media-kling instead.
---

# studio-media-seedance — Seedance 2.0 video generation

The **multimodal** rendering engine of the **`studio-*`** family: nine reference
images, reference *videos* and *audio*, native synced sound, and an intelligent
duration mode none of the others have.

Rendered with **`bytedance/seedance-2.0` on Replicate**
(<https://replicate.com/bytedance/seedance-2.0>) through the shared runner —
`studio run --model seedance`. There is no separate submitter and no MCP path:
one command records the run, mints the presigned URLs, polls, and archives the
finished video into the run.

> **Which engine?** This skill is **Seedance 2.0**. For the **Kling 3.0 / O3
> Omni** models — also on Replicate — use **`studio-media-kling`**: different
> constraints (3–15 s, native multi-shot to 6 cuts, a start frame that combines
> with references) and a **different wording list**, so a draft written for one
> may want rephrasing for the other.

The family:
- **`studio-media-core`** — the runner, the registry, and what validates before
  anything bills. Everything on this page runs through it.
- **`studio-media-prompt`** — author the prompt as structured JSON (camera /
  subject / action / scene / lighting / style / audio, multi-shot timelines).
  Its `input` object drops straight into `--input-file`. Use it for tight or
  repeatable control; plain prose is fine for a quick one-off.
- **`studio-media-character`** — for a video of a known/recurring character: it
  supplies the character's bible and the reference images this engine requires.
  **FIRST load `studio-media-character`** — never generate a character from a
  text prompt alone (see "Reference images are MANDATORY" below).
- **`studio-media-s3`** — where references and outputs live, and how they are
  addressed.

## The model: `bytedance/seedance-2.0`

Multimodal video generation with **native audio**, multimodal reference inputs
(images / video / audio), and intelligent duration control. Output is a single
video file.

### Input schema

| Field | Type | Default | Notes |
|---|---|---|---|
| `prompt` | string (**required**) | — | Max 4000 chars; keep under ~600 English words. Put **spoken dialogue in double quotes** to drive audio. For tight camera/subject/scene control, a multi-shot timeline, or reusable templates, author it as structured JSON via the **`studio-media-prompt`** skill and pass its `input` here. |
| `image` | uri | null | First-frame image for image-to-video. **Cannot** be combined with `reference_images`. |
| `last_frame_image` | uri | null | Last-frame image. Only works when `image` is also set. Not combinable with reference images. |
| `reference_images` | uri[] (≤ 9) | `[]` | For **character consistency**, style, and scene composition. Reference them in the prompt as `[Image1]`, `[Image2]`, … **Cannot** be combined with `image`/`last_frame_image`. |
| `reference_videos` | uri[] (≤ 3, ≤ 15s total) | `[]` | Motion transfer / style / editing. Reference as `[Video1]`, … |
| `reference_audios` | uri[] (≤ 3, ≤ 15s total) | `[]` | Audio-driven generation / lip-sync. Requires ≥1 reference image or video. Reference as `[Audio1]`, … |
| `duration` | int | `5` | 1–15 seconds. Set to `-1` for intelligent duration (model picks length). |
| `resolution` | enum | `720p` | `480p` · `720p` · `1080p` · `4k` (4K = 10-bit H.265/HEVC). |
| `aspect_ratio` | enum | `16:9` | `16:9` · `4:3` · `1:1` · `3:4` · `9:16` · `21:9` · `9:21` · `adaptive`. |
| `generate_audio` | bool | `true` | Synced dialogue, SFX, and music. |
| `seed` | int | null | Set for reproducible generation. |

Key constraint: **`image`/`last_frame_image` and `reference_images` are mutually
exclusive.** Use `image` for a specific first frame; use `reference_images` when
you want a character/style carried across a freshly composed scene. The runner
enforces this locally rather than letting Replicate reject a billed request.

`studio models show seedance` prints the live schema; it is authoritative over
this table.

## Approval gate (MANDATORY) — the FULL payload

**Show the user the complete payload as the two documents — `PROMPT` then
`INPUT` — and wait for explicit approval before submitting.** Every parameter,
not just the prompt text: a wrong `resolution` or a wrong `duration` bills
exactly like a wrong prompt. Re-approve after **any** edit. A yes given to a
plan, to a menu answer, or to a payload shown several messages ago is not
approval of the request about to be sent.

`--dry-run` renders exactly that review and bills nothing.

## Wording

Name the wardrobe explicitly and let build words — strong, muscular,
broad-shouldered — carry the physique.

`studio prompt` checks a draft against this model's wording list and suggests
the preferred alternative where one is recorded; see
`studio phrasebook show --model seedance`.

## Invoke

```bash
# input.json = the built `input` object WITHOUT image/reference fields
#   (studio-media-prompt: studio prompt prompt.json --emit input  → the .input object)
studio run \
  --model seedance --project <project> --input-file input.json \
  --character <name> --slots 1,2,3,6 --name <file> --poll
```

The runner serves every registered model, image and video. It records the run
before submitting, resolves the character's selection to paths, mints fresh
presigned URLs at submit time (dropping any image/reference fields baked into
the input file), and on `--poll` archives the finished video into the run.
`--slots` picks positions **within the resolved selection**, which is what
`[Image1..N]` refers to; omit it to send the whole selection. `--dry-run` prints
the payload and bills nothing.

**`--project` is required and never inferred.** Where output lands is the one
thing rerunning a command cannot undo, so it is asked for rather than guessed.

**Never paste a presigned URL by hand.** They are ~2 KB each, they expire, and a
single mistyped character yields an expired fetch and a dead — often billed —
render. The runner mints them in the same step that submits, so none passes
through the agent context.

**Never `Prefer: wait` on a video job.** Seedance renders take longer than the
60 s wait window, and a timed-out wait retries internally, creating **duplicate
predictions that all bill**. The runner creates and then polls, which is what
`--poll` does.

### Chaining — animate a frame from a studio-media-image run

```bash
studio run \
  --model seedance --project <project> --input-file input.json \
  --start-run <project>/latest#1 --name <file> --poll
```

`--start-run` / `--end-run` bind an earlier run's output to `image` /
`last_frame_image`; `--ref-run` adds a run's output as reference material;
`--start-key` / `--end-key` / `--key` take an explicit path. Since `image` and
`reference_images` are mutually exclusive here, the runner **refuses** a start
frame combined with `--character`/`--ref-run` rather than letting Replicate
reject it — a start frame already carries identity. (On Kling the two combine
freely, so the same command with `--model kling` is allowed.)

### Output — the run owns it

Generated videos are stored in the media library, never in git, and every
submission is a **run** under the **project**:

```
<project>/runs/<YYYY-MM-DD_HH-MM-SS>_<slug>/
    request.json    what we sent — references as paths, never signed URLs
    prompt.json     the studio-media-prompt source, when one was used
    result.json     prediction id, status, media types, output keys
    output/         the rendered video
```

A run belongs to a project, not to a character: one piece of work can involve
several characters, and `request.json` records `characters[]` alongside
`project` so "every run using this character" stays answerable. There is no
`misc` owner and no per-character `output/` folder — that shape is what the
two-tree split abolished.

`--poll` archives the finished video into its run automatically, so there is no
separate upload step, and the flow stays download-then-upload — video bytes
never pass through the agent context.

```bash
studio runs list <project>
studio runs show <project>/latest
studio runs outputs <project>/latest --presign
studio runs find --character <name>
```

Minimal example input:

```json
{
  "prompt": "A golden retriever runs across a sunny beach, waves crashing. \"Come on, let's go!\"",
  "duration": 5,
  "resolution": "1080p",
  "aspect_ratio": "16:9"
}
```

### Reference images are MANDATORY for any character video

**Rule (non-negotiable): never generate a video of a known character without
sending that character's reference images.** A text prompt alone drifts
off-model. If you are about to submit with only a `prompt` for a character,
STOP and load **`studio-media-character`** first.

- Seedance 2.0 accepts up to **9** `reference_images`. Reference them in the
  prompt as `[Image1]`, `[Image2]`, …
- **Slot N is position N in the resolved selection** — not a trailing file
  number. Numbers in filenames are unique only within a group, so reading one as
  a slot aims an instruction at whatever happens to sit in that position.
- Each character's reference library is **indexed in its bible**, and a
  selection is named (`--pick`, `--pick-tag`) or comes from `default_set`. An
  over-cap selection is refused rather than truncated.
- `reference_images` **cannot** be combined with `image` / `last_frame_image`.

### How reference images reach Replicate

Replicate accepts a file input as a URL. References live in the media library,
so the path is a short-lived **presigned HTTPS URL** minted by the API: the
store stays private, Replicate fetches the object during the job, and only a
short URL — never the bytes — exists anywhere. **No `REPLICATE_API_TOKEN` is
needed here for anything**: the API holds the provider credential and does the
submitting, so the CLI never has one.

Normally you never do this by hand: `--character <name>` on the runner resolves
the selection and presigns it. To look at what a selection resolves to first:

```bash
studio character refs <name> --describe
studio character refs <name> --pick-tag face --presign --json > refs.json
# -> [{ "node": "node-…", "name": "<file>.jpg", "url": "…" }, …]
```

`refs` resolves the **bible's index** — which is why the index exists. Do not
substitute a folder listing for it: `reference/` holds purpose subfolders
(`face/`, `body/`, `wardrobe/` …), listings are one folder deep, and the folder
does not say what any image shows. `studio presign --folder` is for a folder of
files you already know, e.g.:

```bash
studio presign --folder <name>/reference/face --json
```

### THE RULE — the store is the only origin

**Assets are never uploaded to Replicate.** Everything sent to a model must
already be in the media library and reaches Replicate only as a short-lived
presigned URL minted at submit time. For an ad-hoc local image, put it in the
library first — `studio upload` mints the catalog record and the presigned PUT
together, so no cloud credential is involved:

```bash
studio upload --folder <name>/corpus <img>
```

A character has four pools — `reference/`, `corpus/`, `seed/`, `archive/` — and
which one a file belongs in is a decision, not a default. Working material for a
piece of work goes in the **project's** input pool instead
(`studio projects add-inputs <img> <project>`).

The two former escape hatches — one that POSTed bytes to Replicate's Files
API, one that inlined them as a base64 data URL — have been **removed**: both
sent assets to Replicate, and the data-URL path also burned ≈1 token per
character of agent context.

Signed URLs are also never *stored*: `request.json` records paths, and the run
store refuses a URL-shaped binding. Paths are stable, so any run replays by
re-minting fresh URLs.

### Full-res references, zero context cost

**Seedance and Replicate do NOT require tiny references** — sharper references
give better character consistency, and presigned URLs carry full-resolution
images at zero context cost. The API sets the URL's lifetime and `--expires` is
accepted and ignored — it is comfortably longer than a render job. See the
**`studio-media-s3`** skill for details and for `studio login`.

## Characters

Characters are **data, not skills** — a single **`studio-media-character`** skill
manages them all, and each one is a row carrying its bible and a described set
of references. To generate an
on-model character video, load **`studio-media-character`**: it reads the bible
and resolves the reference selection; this engine skill is character-agnostic. A
character's rendering style is chosen per video (realistic by default, or an
optional stylized look from its bible) rather than fixed by the engine.
