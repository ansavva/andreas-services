---
name: studio-media-seedance-2-5
description: Generate videos with ByteDance Seedance 2.5 via `studio run --model seedance-2.5` — the successor to Seedance 2.0 and the engine to reach for when a character SPEAKS: better dialogue timing and lip-sync, a true 30-second ceiling in one pass, up to 30 reference images, and a seed. Covers what it changes against 2.0, the two things it lost on Replicate (no 1080p, no 4k), the aspect-ratio rule that first+last-frame mode imposes, and how a talking-head clip is prompted. Pair with studio-media-prompt (--engine seedance) and studio-media-character. For the 2.0 model use studio-media-seedance.
---

# studio-media-seedance-2-5 — Seedance 2.5

The talking engine. Where `studio-media-seedance` (2.0) is the multimodal
generalist, 2.5 is the same family tuned for **production dialogue**: speech in
double quotes drives voice and lip movement in the same pass as the picture,
and the timing lands where the words are. Reach for it whenever a clip has
someone talking to camera. Rendered with **`bytedance/seedance-2.5` on
Replicate** through the shared runner: `studio run --model seedance-2.5`.

> Invocation, hard rule #2, run recording and validation are shared — see
> [`studio-media-core`](../studio-media-core/SKILL.md), and `studio models show
> seedance-2.5` for the live schema. `studio-media-seedance` documents the
> family's prompting and reference rules, which hold here unchanged; this page
> is only what 2.5 does differently.

## What changed against 2.0

| | `seedance` (2.0) | `seedance-2.5` |
|---|---|---|
| Dialogue | in quotes, native audio | in quotes, native audio, **noticeably better lip-sync and rhythm** |
| Duration | 1–15 s | **4–30 s** in one pass, or `-1` to let the model choose |
| Reference images | ≤9 | **≤30**, plus ≤10 videos and ≤10 audios (30 s combined each) |
| Resolution on Replicate | 480p · 720p · 1080p · 4k | **480p · 720p only** |
| Aspect ratio | fixed list | the list plus **`adaptive`** |
| Seed | yes | yes ("not guaranteed") |
| Output | mp4 | mp4 or mov (`output_format`) |
| Watermark | — | `watermark`, default off |

**The resolution row is the trade.** Nothing above 720p exists on Replicate's
2.5 tier, so a 9:16 clip comes back 720×1280 and is upscaled to 1080×1920 at
export. For a talking head that is the right trade; for a wide product shot
where pixels matter more than speech, render on `seedance` at 1080p.

## Cost

Per second of output, audio included, Replicate September 2026:

| Resolution | Text / image inputs | With a reference **video** |
|---|---|---|
| 480p | $0.1028 | $0.4304 |
| 720p | **$0.2312** | $0.9676 |

A 14 s talking-head clip at 720p is about $3.25. A reference video quadruples
the rate — bind one only when the motion genuinely has to come from footage.

## Invoke

```bash
# prompt.json authored with studio-media-prompt; dialogue as a `dialogue` array
studio prompt prompt.json --engine seedance > compiled.json
# input.json = compiled.json's `input` object (no image fields)
studio run --model seedance-2.5 --project <project> \
  --input-file input.json --prompt-json prompt.json \
  --start-run <project>/latest#1 --name <file> --poll
```

`--engine seedance` is right for both Seedance models: the engine profile
routes `technical` fields the same way, and the registry refuses a value 2.5
does not take (`resolution: 1080p` fails validation before anything bills).

## Inputs that matter

- **`duration`** — an integer **4–30**, or `-1`. Count the words: spoken pace is
  about three words a second, so 14 s carries ~40 words with pauses. `-1` is
  worth trying for dialogue — the model picks the length the lines need.
- **`resolution`** — `720p`. There is no higher tier; `480p` only for drafts.
- **`aspect_ratio`** — `9:16` for a reel from a 9:16 still. **`adaptive` is
  required** in first+last-frame, editing and extension modes; a plain
  image-to-video shot (start frame only) takes the explicit ratio.
- **`seed`** — set one. Reproducibility is not guaranteed, but a retake that
  changes one line is far closer with the seed held.
- **`generate_audio`** — `true` (the default). Turn off only for a silent
  b-roll shot; music is better added in post than baked in.

## Start frame or references, never both

Unchanged from 2.0 and enforced locally: `image` / `last_frame_image` **cannot**
be combined with `reference_images`, `reference_videos` or `reference_audios`.
A start frame already carries identity, so the runner refuses `--character`
or `--ref-run` alongside `--start-run` rather than letting Replicate reject a
billed request. For an on-model character in a *new* composition, use
references (up to 30) and `[Image1]…` tokens; for an approved still, use the
frame.

## Prompting a talking head

The README asks for a "production brief" prompt — structured, specific — which
is exactly what `studio-media-prompt` emits. For dialogue:

- Put each spoken line in the `dialogue` array; it is serialised in double
  quotes, which is what drives the voice.
- Describe the **voice** in `audio` ("warm low baritone, deadpan, unhurried"),
  and say **no music** if music goes on in post.
- Give the physical beats in `action` and tie them to words ("a slow
  head-shake on 'not even me'") — 2.5 follows these; 2.0 mostly did not.
- With a start frame, drop `scene` and `lighting` and shrink `subject` to an
  identity anchor, as `studio-media-kling` explains.
- Add "burned-in subtitles or captions" to `negative`. Captions are added in
  post, and a model that renders its own cannot be corrected.

## Failure modes

- **Words compressed or dropped.** Too many for the duration. Cut words before
  adding seconds, or set `duration: -1`.
- **A name mispronounced.** Respell it phonetically in the dialogue line and
  keep the on-screen caption correct.
- **The clip came back 720p.** Expected — see the resolution row. Upscale at
  export; do not resubmit.
- **`aspect_ratio` rejected.** You bound a last frame or a reference video
  with a fixed ratio. Set `adaptive`.
- **A 3 s draft refused.** The floor is 4 s on this model.
- **Bill four times what was expected.** A reference video was bound; the
  `video_in` tier applies to the whole render.
- **`E005 The input or output was flagged as sensitive`.** A kiss between two
  adults — fully clothed too, and with a start frame that is already a kiss
  still. Not billed, and no wording gets past it. Kling and Veo render the
  same clip; the map is on
  [`studio-media-scene`](../studio-media-scene/SKILL.md#what-each-engine-will-actually-render--contact-between-two-people).

## Formats and caps

Images `.jpg .jpeg .png .webp .gif .bmp` (the README names none; the family's
list is assumed). Reference images ≤30, videos ≤10 and ≤30 s combined, audios
≤10 and ≤30 s combined, audios requiring at least one image or video. Prompt
ceiling assumed 4000 characters as on 2.0; the README states none.
