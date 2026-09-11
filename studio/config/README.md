# `studio/config/` — shared config assets

Material that belongs to no character and no project. That means **angle
images**: one per body or head orientation, used as a framing guide when a
turnaround renders a character's standard set. They are the only shared material;
the phrasebook and the templates are catalog rows, so there is nothing else to
seed.

```
config/angle/face/*.png    eight orientations
config/angle/body/*.png    six of the same eight
config/angle/source/       the sheets the angle images were cut from
config/angle/prompts/*.md  prompts to regenerate either set
```

The eight, in turn order: `front`, `three-quarter-right`, `profile-right`,
`three-quarter-back-right`, `back`, `three-quarter-back-left`, `profile-left`,
`three-quarter-left`. **The body set has six** — the two front three-quarters
are absent; see below. `source/` holds the sheets so the splits stay
reproducible; it is not a picture of anybody, so it belongs to no character.

## This directory is the source of truth; the library holds a copy

`studio config sync` lists every angle image with no node; `studio config sync
--apply` uploads them, as nodes, through the API. `scripts/dev-setup.sh` runs it
and `scripts/dev-shared-material.sh` wraps it. Two rules follow:

- **Edit here, never in the library.** The push is one-way and additive — it
  uploads only the angle images with no node and never deletes — so an object
  edited in the bucket survives until the file of the same name changes here.
- **A model only ever sees the library copy.** Assets reach Replicate as a
  short-lived presigned URL of an S3 object, never as bytes from disk, and an
  angle image with no node is invisible to a turnaround: it refuses before
  spending and names `dev-setup.sh` as the fix.

The turnaround itself is built in the app, on a run's plan editor. The angle
templates that bind these images are catalog rows: the app edits them at
`/templates`, and `studio templates pull`, `push` and `show` move them between
stacks. Only body angles bind an image; a face angle binds none.

## What an angle image is, and what it is not

An angle image says **how to stand**, nothing else. Each prompt that binds one
says so explicitly — match the stance, the direction the body and head face, and
the framing, and take nothing else from it. That wording is load-bearing: an
unqualified reference image invites a model to blend it, which would put a grey
mannequin's proportions into a character's body. So an angle image is
deliberately **anonymous**: an untextured, featureless figure carrying no
identity. It lives here and never inside a character's pools, where `--pick-tag
body` could hand a model a stranger's sculpt as one of the character's own slots.

**An angle image's name is the edge of the frame its face points toward.**
`-left` means the nose points at the left edge; equivalently, that side of the
head is toward the camera. Name from the pixels, never from a caption: the head
sheet's own captions have the two back three-quarters swapped.

**A back three-quarter is not a profile.** It shows the back of the head filling
most of the frame with a narrow sliver of face breaking the silhouette, so the
slot prompts turn the shoulders with the head and forbid the profile outright.
Where only one side exists in a source, its twin is a horizontal mirror — the
same sculpt, a consistency no second render could match.

## Provenance, and how to replace the body angle images

The **face** angle images are cut from `angle/source/head-sheet.png` with
`pipeline/scripts/split_angle_sheet.py` — measured cuts, so every angle image is
the same sculpt; a model asked to isolate a tile re-draws the sculpt instead. The
**body** angle images come from `angle/source/body-sheet.jpg`, a third-party 3D
anatomy study, cut the same way and then upscaled onto white by gpt-image-2 — an
upscale and a background change only, which a model holds reliably where "rotate
this figure to 45 degrees" does not.

**`three-quarter-left` and `three-quarter-right` do not exist in the body group,
and should not be recreated.** Their source figure is refused as sensitive
content — four refusals across gpt-image-2 and gpt-image-1.5, as the subject of
an upscale and as a mere pose guide. A slot nobody can render is worse than an
absent one: it reads as coverage, and one refusal aborts the batch around it. The
remaining six give front, both profiles, back and both back three-quarters, which
is what a build reference is mostly for.

The sources are generic, unbranded and used privately, but not originally ours.
For a set with no third-party lineage, regenerate and keep the filenames:

```bash
# one sheet, then split it into angle images with the same script
studio run --model gpt-image-2 --project <project> --name angle-sheet --no-refs \
  --prompt-file config/angle/prompts/body-sheet.md --dry-run
uv run --script pipeline/scripts/split_angle_sheet.py <the sheet> --out config/angle/body
```

`config/angle/prompts/face-sheet.md` generates a head sheet from scratch. Every
consumer addresses an angle image by filename, so swapping the images is a
drop-in: nothing in the templates or the code changes.
