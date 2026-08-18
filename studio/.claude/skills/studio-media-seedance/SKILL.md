---
name: studio-media-seedance
description: Generate videos with ByteDance Seedance 2.0 via the Replicate MCP — the scripted/API engine of the studio-* family. Use whenever the user wants to create, generate, or render a video, clip, animation, or motion piece (with optional native audio, first/last-frame images, or reference images/videos/audio). Covers the model input schema, the create-then-poll flow, output naming, and how images reach Replicate (presigned S3 URLs). Part of the studio-* family: pair with studio-media-prompt (--engine seedance) to author the prompt and studio-media-character for on-model character videos. For renders on the Kling models use studio-media-kling instead.
---

# studio-media-seedance — Seedance 2.0 video generation

The **scripted/API** rendering engine of the **`studio-*`** family. Generate videos by creating a
Replicate prediction against **`bytedance/seedance-2.0`**
(<https://replicate.com/bytedance/seedance-2.0>) through the **Replicate MCP
server**, polling it, and saving the output MP4 to S3. There is no build step —
the "work" is the MCP call, the poll, and the download.

> **Which engine?** This skill is **Seedance 2.0**. For the **Kling 3.0 / O3 Omni**
> models — also on Replicate — use **`studio-media-kling`**: different constraints
> (3-15s, native multi-shot to 6 cuts, no seed) and, importantly, a **different
> wording lists**, so a draft written for one may want rephrasing for the other,
> so don't apply this skill's wording rules there.

The family:
- **`studio-media-prompt`** — author the prompt as structured JSON (camera / subject /
  action / scene / lighting / style / audio, multi-shot timelines). Its `input`
  object drops straight into the call below. Use it for tight or repeatable
  control; plain prose is fine for a quick one-off.
- **`studio-media-character`** — for a video of a known/recurring character: it
  supplies the character's bible and the reference images this engine requires.
  **FIRST load `studio-media-character`** — never generate a character from a text
  prompt alone (see "Reference images are MANDATORY" below).
- **`studio-media-s3`** — the `studio-prod-media-us-east-1` asset store references and
  outputs live in.

## The model: `bytedance/seedance-2.0`

Multimodal video generation with **native audio**, multimodal reference inputs
(images / video / audio), and intelligent duration control. Output is a single
video file URL.

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
you want a character/style carried across a freshly composed scene.

## Prompt approval gate (MANDATORY)

**Before submitting any prompt to the model, show the user the exact final
prompt text and wait for their explicit approval. Do not call
`create_models_predictions` until they say yes.** Re-approve after any edit to
the prompt. The gate covers the prompt sent to the model — the surrounding steps
(presigning references, downloads, uploads, polling) do not need approval. This
keeps output on-brief and avoids failed/billed renders.

## Wording

Name the wardrobe explicitly and let build words — strong, muscular,
broad-shouldered — carry the physique.

`studio prompt` checks a draft against this model's wording list and suggests
the preferred alternative where one is recorded; see
`studio phrasebook show seedance`.

## Submit with FRESH presigned URLs minted in code (MANDATORY)

**Never hand-paste presigned reference URLs into a prediction call, and never
reuse presigned URLs across calls.** They are ~2 KB each, expire, and a single
mistyped character yields a 400/expired fetch and a dead (often billed) render.
Instead, **mint fresh presigned URLs from code at the moment you submit**, using
the existing presign code, and submit in the same step.

Use the helper — it presigns the character's reference set fresh and POSTs the
prediction directly to the Replicate HTTP API (needs `REPLICATE_API_TOKEN`), so
no URL passes through the agent context:

```bash
# input.json = the built `input` object WITHOUT image/reference fields
#   (studio-media-prompt: studio prompt prompt.json --emit input  → the .input object)
set -a; . ./.env; set +a
studio run \
  --model seedance --project <project> --input-file input.json \
  --character <character> --slots 1,2,3,6 --slug <slug> --poll
```

The helper serves **both** video engines (`--engine seedance|kling`), records the
run, mints references fresh (deleting any image/reference fields baked into the
input file), and on `--poll` archives the finished video into the run.
`--slots` picks which reference numbers map to `[Image1..N]` in order; omit it to
use the whole set. `--dry-run` prints the payload and bills nothing. Only fall
back to the MCP `create_models_predictions` tool for a job with no images at all
— and then record the run by hand.

### Chaining — animate a frame from a studio-media-image run

```bash
studio run \
  --model seedance --project <project> --input-file input.json --project <project> \
  --start-run <project>/latest#1 --slug <slug> --poll
```

`--start-run` / `--end-run` bind an earlier run's output to `image` /
`last_frame_image`; `--ref-run` adds a run's output as reference material. Since
`image` and `reference_images` are mutually exclusive here, the helper **refuses**
a start frame combined with `--character`/`--ref-run` rather than letting Replicate
reject it — a start frame already carries identity. (On Kling the two combine
freely, so the same command with `--engine kling` is allowed.)

## How to generate a video (MCP fallback, no references)

Use the Replicate MCP tool `create_models_predictions` with
`model_owner: "bytedance"`, `model_name: "seedance-2.0"`, and an `input` object.

**Do NOT set `Prefer: wait` on video jobs.** Seedance renders always take longer
than the 60s wait window, and a timed-out `wait` call retries internally —
creating **duplicate predictions that all bill** (this happened once and spent
~2 clips of compute for one result). Instead, create the prediction with no
`wait`, take the returned `prediction_id`, and poll `get_predictions` until
`status` is `succeeded`, `failed`, or `canceled`. On success, `output` is the
video URL — download it with `curl` and hand the local path back to the user.

If a create call ever errors or times out, **don't blindly re-create it** —
first `list_predictions` (filtered to `bytedance/seedance-2.0`) to see whether a
job is already `processing`/`succeeded`, and `cancel_predictions` any duplicates.

### Output location (always) — the run owns it

Generated videos are stored in **S3** (bucket
`studio-prod-media-us-east-1`), not in git, and every submission is a **run**:

```
projects/<project>/runs/<YYYY-MM-DD_HH-MM-SS>_<slug>/
    request.json    what we sent — references as S3 KEYS, never signed URLs
    prompt.json     the studio-media-prompt source, when one was used
    result.json     prediction id, status, media types, output keys
    output/         the rendered video
```

The owner is the character, or `misc` for a video not tied to one. `--poll`
archives the finished video into its run automatically, so there is no separate
upload step — the flow is still download-then-upload, so video bytes never pass
through the agent context.

Inspect and chain runs with the shared store:

```bash
studio runs list <character>
studio runs show <project>/latest
studio runs outputs <project>/latest --presign
```

There is no longer a per-character `output/` folder; pre-existing videos were
imported into synthetic runs via `studio runs adopt`.

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
passing that character's reference images in `reference_images`.** A text prompt
alone drifts off-model. If you are about to call the model with only a `prompt`
for a character, STOP and load **`studio-media-character`** first.

- Seedance 2.0 accepts up to **9** `reference_images`. Reference them in the
  prompt as `[Image1]`, `[Image2]`, …
- Each character keeps a **fixed, numbered reference set in S3** (at
  `characters/<character>/reference/`), a chosen subset per generation so identity
  stays locked without re-picking. **`studio-media-character`** hands you ordered
  presigned URLs for it (`studio character refs <name> --presign`); under the hood
  that is `studio presign --folder <character>/reference` (below).
- `reference_images` **cannot** be combined with `image` / `last_frame_image`.

### How image files reach Replicate (presigned S3 URLs)

Replicate accepts a file input as a URL or an inline data URL. Since references
and outputs live in **S3**, the primary path is a **presigned HTTPS URL**: the
object stays private, Replicate fetches it via a short-lived signed URL, and only
a short URL (never the bytes) enters the agent context. No `REPLICATE_API_TOKEN`
is needed for references.

```bash
# References for a character — ordered presigned URLs (via studio-media-character)
studio character refs <character> --presign --json > refs.json
# equivalently, straight from the studio-media-s3 skill:
studio presign --folder <character>/reference --json > refs.json
# -> [{ "key": "characters/<character>/reference/face/<character>_1.webp", "url": "…" }, …]
# Pass the .url values as reference_images; <character>_1 -> [Image1], <character>_2 -> [Image2], ...

```

### THE RULE — S3 is the only origin

**Assets are never uploaded to Replicate.** Everything sent to a model must
already be an S3 object and reaches Replicate only as a short-lived **presigned
URL** minted at submit time. For an ad-hoc local image, upload it to S3 first,
then reference its key:

```bash
studio upload --folder <character>/originals <img>
```

The two former escape hatches — one that POSTed bytes to Replicate's Files
API, one that inlined them as a base64 data URL — have been **removed**: both
sent assets to Replicate, and the data-URL path also burned ≈1 token per
character of agent context.

Signed URLs are also never *stored*: `request.json` records S3 keys, and
the run store refuses a URL-shaped binding. Keys are stable, so any run replays by
re-minting fresh URLs.

### Full-res references, zero context cost

**Seedance and Replicate do NOT require tiny references** — sharper references
give better character consistency, and presigned S3 URLs carry full-resolution
images at zero context cost (only the short URL enters the agent context, and
through the runner, not even that). Presigned URLs default to a 1 h
expiry (`--expires` to change) — plenty for a render job. See the **`studio-media-s3`** skill
for details and `aws login` setup.

## Available Replicate MCP tools (common)

- `get_models` / `get_models_readme` — inspect a model's schema and docs.
- `create_models_predictions` — run an official model (this one).
- `get_predictions` / `list_predictions` — poll or list runs.
- `cancel_predictions` — cancel a running job.
- `search` / `search_docs` — find models and client usage docs.

Always pass a `jq_filter` to these tools to keep responses small (e.g.
`{id, status, output, error}` when polling).

## Characters

Characters are **data, not skills** — a single **`studio-media-character`** skill
manages them all, and each one is an S3 record (`characters/<name>/` with a
`profile.yaml` bible and a described `reference/` library). To generate an
on-model character video, load **`studio-media-character`**: it reads the bible and
hands you the fixed reference set as ordered presigned URLs; this engine skill is
character-agnostic. A character's rendering style is chosen per video (realistic
by default, or an optional stylized look from its bible §5), not fixed by the
engine.
