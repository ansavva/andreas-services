---
name: studio-media-kling-v3-motion-control
description: Transfer the motion of a reference video onto one still with Kling 3.0 Motion Control (kwaivgi/kling-v3-motion-control) on Replicate, as a recorded run. Reach for it when the movement already exists as footage — a dance, a gesture, a piece of blocking — and the job is to make a character perform it; the still supplies the look, the clip supplies every frame's pose and the output's length. Not a text-to-video engine: it takes no duration, aspect ratio, reference set or last frame. For a shot directed from a prompt use studio-media-kling; for a clip that needs changing use studio-media-grok-imagine-video.
---

# studio-media-kling-v3-motion-control — Kling 3.0 Motion Control

The motion-transfer engine of the `studio-*` family. Every other video engine
here is *directed*: a prompt says what happens and the model invents the
movement. This one is *driven*: a reference clip says what happens, frame by
frame, and the model only has to make `<name>` do it. Reach for it when the
motion is the hard part and already exists as footage.

Rendered with **`kwaivgi/kling-v3-motion-control` on Replicate**. Same family
as `studio-media-kling`, same S3-only flow, a different job: the omni model
takes `reference_video` as one influence among several; this one takes `video`
as the skeleton of the output.

The family:
- **`studio-media-image`** — makes the still. A full-body frame of `<name>`
  from an image engine is the usual input.
- **`studio-media-kling`** — the directed sibling. Use it when there is no
  footage to copy.
- **`studio-media-scene`** — a motion-control clip is a run like any other and
  chains and assembles the same way.

## The model

`kwaivgi/kling-v3-motion-control` — <https://replicate.com/kwaivgi/kling-v3-motion-control>

| Input | Notes |
|---|---|
| `image` | **Required.** The look: character, background, everything visible. One `.jpg/.jpeg/.png`, max 10 MB, 340–3850 px a side, aspect 1:2.5–2.5:1. |
| `video` | **Required.** The motion: the character in the output moves as the one in this clip does. `.mp4/.mov`, max 100 MB, 3–30 s. |
| `prompt` | Adds elements and effects; it does not direct the movement. The model allows it empty; `studio run` still asks for one, so name what the still shows and what the motion is. |
| `character_orientation` | `image` = faces the way the still does, **clip capped at 10 s** · `video` = faces the way the footage does, **clip up to 30 s**. Default `image`. |
| `mode` | `std` = 720p · `pro` = 1080p. Default `pro`. |
| `keep_original_sound` | Default true: the reference clip's audio carries over. Set false for a silent output. |

**No `duration`, `aspect_ratio`, `reference_images`, `end_image`, `seed` or
`negative_prompt`.** The output is as long as the reference clip and shaped by
the still. Nothing here holds a character on-model beyond the one still, so the
still has to be right before anything bills.

### Cost

| Mode | Per second of output |
|---|---|
| std (720p) | **$0.07/s** |
| pro (1080p) | $0.12/s |

Billed on *output* seconds, which equal the reference clip's. A 10 s clip is
$0.70 at `std`, $1.20 at `pro` — the cheapest video seconds in the registry.
Iterate at `std`; the mistakes are in the pairing, not the resolution.

## Hard constraints

| | |
|---|---|
| Still | `.jpg/.jpeg/.png` only — **`.webp` is refused up front**; `studio convert --for kling-v3-motion-control` fixes it |
| Still size | 340–3850 px, 1:2.5–2.5:1, ≤10 MB |
| Clip | `.mp4/.mov`, ≤100 MB, 3–30 s |
| Clip length at `character_orientation: image` | **≤10 s** |
| Clip length at `character_orientation: video` | ≤30 s |
| Images | exactly one; there is no reference set |

**Both required inputs are checked before a draft is written.** A run
missing `video` is refused at `--dry-run` with the schema's own `required`
list, and the API refuses it again at submit — before the run moves to
`pending`, so nothing wedges.

## Workflow

```bash
# the look — a still already in the library — binds as the first frame (`image`);
# the motion — a clip already in the library — binds as the clip (`video`)
studio run --model kling-v3-motion-control --project <project> \
  --start-run <project>/latest \
  --clip-key <project>/input/<clip>.mp4 \
  --prompt "<name> from the source image, performing the motion in the clip" \
  --extra '{"mode": "std"}' \
  --name <file> --dry-run
```

`--start-run` / `--start-key` bind the still (→ `image`); `--clip-run` /
`--clip-key` bind the clip (→ `video`). `--ref-run`, `--key` and `--character`
have nowhere to go on this model and are refused locally ("takes no reference
list — it has a single image input"). Read the two documents, then submit with
`studio runs submit <run>`. **Every run bills, and the submit command is the
act.**

Both are **sends**: the run records the node, not a URL, so `request.json`
says which clip drove it and the URL is minted at submit. A `.webm` or `.avi`
clip is refused by name — the model takes `.mp4/.mov` — and a `.webp` still
is refused with the `studio convert --for kling-v3-motion-control` line that
fixes it. In the app the same two are the **Start frame** and **Source video** tiles;
the Source video tile's picker lists videos only.

Where a clip comes from:
- **A run's output** — `--clip-run <project>/latest` (or `#2` for the second
  clip that run made).
- **Footage from outside** — `studio upload --folder <project>/input <clip>.mp4`,
  then `--clip-key <project>/input/<clip>.mp4`. Trim to the beat you want
  first: the whole clip is transferred and billed, and 3 s is the floor.

### Output — the run owns it

Every submission is a run under `<project>/runs/<run_id>/`, holding
`request.json`, `result.json`, and `output/` with the video. `--poll` archives
it; a run left unpolled closes on the callback or on `studio runs reconcile`.
Inspect with `studio runs` (`list` / `show` / `outputs --presign`).

## Make the still from the clip's first frame

The transfer holds together when the still's pose and framing already match
the clip's opening frame. Hand it a still in a different pose and the first
second is the model dragging `<name>` into position — and the identity is
what gives. So the still is made *from* that frame, three steps, two of
which bill:

1. **Take the frame the transfer starts from.** For a whole clip that is
   the first frame: the clip's `⋮` menu on a folder tile or a run's output →
   **First frame as · Reference**. For a transfer that starts mid-clip, open
   the clip, play or scrub to the moment, pause, and the same menu (the open
   file's `Use as…`, the opened run's rail) reads **This frame as ·
   Reference** — the frame on screen is the frame taken. The worker cuts it
   into the project's input pool and it lands on the create bar, named for
   the clip and the moment (`<clip>-at-0m06.5s.png`). From a terminal:
   `studio frames at <project>/latest --time 6.5 --add-input`.
2. **Render `<name>` into it.** An image model with the frame as a
   reference and the character's identity images alongside —
   `studio-media-gpt-image-2` by default — with a prompt that names the
   swap: *"`<name>` in exactly this pose, framing and setting; replace the
   person, keep everything else."* Check the result against the frame
   before going on: same crop, same limb positions, whole body visible.
3. **Run the transfer** with that render as `--start-run` and the same clip
   as `--clip-run` (or the Start frame and Source video tiles).

Step 1 is why "First frame as" exists on a clip's menu; a clip attached
as a start frame would be refused, and walking the picker back to a frame
you just cut was the old route.

## Getting the pairing right

The README's tips, restated as the failures they prevent:

- **Match the framing of still and clip.** A full-body clip driving a
  waist-up still — or the reverse — has nowhere to put the legs, and the model
  invents them. Frame the still the way the footage is framed.
- **The whole body and head must be visible in the still**, unobstructed. A
  cropped limb is a limb the model has to draw from nothing on the first frame.
- **Steady, moderate motion transfers; fast or chaotic motion does not.**
  Whip pans, jumps and flailing come back smeared or wrong. Slow the reference
  down in an editor before uploading rather than hoping.
- **`character_orientation` is about which way `<name>` faces, not framing.**
  `image` keeps the still's facing and is the safer default for a talking
  head or a piece to camera; `video` follows the footage and is what a dance
  or a turn needs — and is the only setting that goes past 10 s.
- **The prompt is context, not direction.** It cannot change the movement.
  Use it to name what the still shows and what the motion is ("`<name>` in the
  source image, dancing in the same room"), which helps the model read the
  footage; leave the choreography to the clip.
- **`keep_original_sound` carries the clip's audio, music and all.** For a
  clip with a scratch track or someone else's voice, set it false and add
  sound in assembly.

## Verified runs

**Registered 2026-09-12, dry-run only.** `studio models show` resolves to
`kwaivgi/kling-v3-motion-control`; a `--start-run` still plus a `--clip-run`
clip produced a draft with two send rows — `image · start`, `video · clip` —
and an `INPUT` naming both as presigned nodes, then was discarded. A run
without the clip was refused before the draft. Nothing has billed. The first
real run should be a 3–5 s `std` clip of steady motion and a full-body still,
to measure output size, fps and how well the face survives.
