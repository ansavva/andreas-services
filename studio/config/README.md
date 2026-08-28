# `studio/config/` — shared config assets

Material that belongs to no character and no project. Here that means **pose
plates**: one image per body or head orientation, used as a framing guide when a
turnaround renders a character's standard set.

**The plates are the only shared material left.** `phrasebook/wording.yaml` was
the other, seeded here under the opposite rule — copied in only when the bucket
had none, because from the first `studio phrasebook add` the bucket's copy was
the live document. The phrasebook is `TERM#` rows now, so there is no document
to seed and no second push. `scripts/dev-shared-material.sh` is a wrapper around
`studio config sync` and nothing else.

```
config/pose/face/*.png    eight orientations
config/pose/body/*.png    six of the same eight
config/pose/source/       the sheets the plates came from
config/pose/prompts/*.md  prompts to regenerate either set
```

The eight, in turn order: `front`, `three-quarter-right`, `profile-right`,
`three-quarter-back-right`, `back`, `three-quarter-back-left`, `profile-left`,
`three-quarter-left`. **The body set has six of them** — the two front
three-quarters are gone; see below.

`source/` holds the sheets the plates were cut from, kept so the splits stay
reproducible. It lived inside a character's pools for a while —
first `reference/`, where it was indexed as that character's identity, then
`corpus/`. Both were wrong for the same reason: it is not a picture of anybody,
so it belongs to no character.

## This directory is the source of truth; S3 holds a copy

`studio/scripts/dev-setup.sh` pushes it into the library through
`studio config sync --apply`, and `domain/paths.py` builds keys under that root.
Two rules follow:

- **Edit here, never in the library.** The push is one-way and additive — it
  uploads only the plates with no node and never deletes — so an object edited
  in the bucket survives until someone changes the file of the same name here.
- **A model only ever sees the S3 copy.** Assets reach Replicate as a
  short-lived presigned URL of an S3 object and never as bytes from disk, so a
  plate that has not been synced cannot be used. `studio character turnaround` checks
  for them first and tells you to re-run `dev-setup.sh` if any are missing.

The angle spec (`pipeline/src/studio_pipeline/domain/templates/reference_angles.yaml`)
names each plate by its S3 key, so the prompt lives in source control and the
image it refers to lives in the bucket.

## What a plate is, and what it is not

A plate says **how to stand**, nothing else. Each prompt that binds one says so
explicitly — match the stance, the direction the body and head face, and the
framing, and take nothing else from it. That wording is load-bearing: an
unqualified reference image invites a model to blend it, which would put a grey
mannequin's proportions into a character's body.

So a plate is deliberately **anonymous**: an untextured, featureless figure. It
carries no identity, and it is not a character reference. A generic anatomy sheet
did once sit inside a character's `reference/body/`, indexed as identity and
tagged `body`, which meant `--pick-tag body` could hand a model a stranger's
sculpt as one of that character's own reference slots. That is the mistake this
directory exists to make impossible.

**A plate's name is the edge of the frame its face points toward.** `-left`
means the nose points at the left edge; equivalently, that side of the head is
toward the camera — the two always coincide, so there is one rule and not two.
Name from the pixels, never from a caption: the head sheet's own captions have
the two back three-quarters swapped relative to its front labels, and naming from
the subject's own left and right is what once produced a prompt instructing two
opposite rotations in the same sentence.

**A back three-quarter is not a profile.** Its plate shows the back of the head
filling most of the frame with only a narrow sliver of face breaking the
silhouette — brow, cheekbone, the tip of the nose. Naming it by the frame edge
alone does not say that, and a prompt that gave only the edge produced a
90-degree profile head on a torso square to the camera, twice. The slot prompts
therefore also turn the shoulders with the head and forbid the profile outright.

Where only one side exists in a source, its twin is a horizontal mirror — the
same sculpt, which is a consistency no second render could match.

## Provenance, and how to replace the body plates

The **face** plates are cut straight from `pose/source/head-sheet.png` with
`pipeline/scripts/split_pose_sheet.py` — measured cuts, so the split is
reproducible and every plate is the same sculpt. gpt-image-2 was tried first on
one tile: it isolated the right cell and gained resolution, but re-drew the
sculpt, and a guide set cannot afford to drift between plates.

The **body** plates come from `pose/source/body-sheet.jpg`, a third-party 3D
anatomy study, cut the same way and then upscaled onto white by gpt-image-2 — an
upscale and a background change only, which the model holds reliably where
"rotate this figure to 45 degrees" does not. Two attempts at projecting a body
from a head plate both came back near-front-on regardless of the angle asked
for, so that route was abandoned.

**`three-quarter-left` and `three-quarter-right` no longer exist in the body
group, and should not be recreated.** Their source figure is refused as
sensitive content: twice by gpt-image-2 and once by gpt-image-1.5 as the subject
of an upscale, and again by gpt-image-2 as a mere pose guide, with the rest of
the figure never drawn. Four refusals across two models is enough — the plates
and their two slots were dropped rather than kept as work that fails at spend
time. A slot nobody can render is worse than an absent one: it reads as
coverage, and one refusal aborts the whole batch around it.

That leaves the body turnaround without its front quarters. The remaining six
still give front, both profiles, back and both back three-quarters, which is
what a build reference is mostly for.

These are generic, unbranded and used privately, but not originally ours — if you
want a set with no third-party lineage, regenerate and keep the filenames:

```bash
# one sheet, then split it into plates with the same script
studio run --model gpt-image-2 --project <project> --name pose-sheet --no-refs \
  --prompt-file config/pose/prompts/body-sheet.md --dry-run
uv run python pipeline/scripts/split_pose_sheet.py <the sheet> --out config/pose/body
```

`config/pose/prompts/face-sheet.md` holds a prompt for generating a head sheet
from scratch, for the case where no source sheet exists.

Because every consumer addresses a plate by filename, swapping the images is a
drop-in: nothing in the spec or the code changes.
