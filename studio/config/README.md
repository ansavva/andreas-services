# `studio/config/` — shared config assets

Material that belongs to no character and no project. Today that means **pose
plates**: one image per body or head orientation, used as a framing guide when a
reference shoot renders a character's standard set.

```
config/pose/body/{front,three-quarter-left,three-quarter-right,profile,
                  back,back-three-quarter}.png
config/pose/face/{front,three-quarter-left,three-quarter-right,profile}.png
```

## This directory is the source of truth; S3 holds a copy

`studio/scripts/dev-setup.sh` syncs it to `s3://<media bucket>/config/`, and
`domain/paths.py` builds keys under that root. Two rules follow:

- **Edit here, never in S3.** The sync is one-way and additive
  (`aws s3 sync --size-only`, never `--delete`), so an object edited in the
  bucket survives until someone changes the file of the same name here.
- **A model only ever sees the S3 copy.** Assets reach Replicate as a
  short-lived presigned URL of an S3 object and never as bytes from disk, so a
  plate that has not been synced cannot be used. `studio character shoot` checks
  for them first and tells you to re-run `dev-setup.sh` if any are missing.

The shot spec (`pipeline/src/studio_pipeline/domain/templates/reference_shots.yaml`)
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

Profiles and three-quarters face **frame right** by convention, so a plate and a
prompt can never disagree about which way the nose points. The
`three-quarter-left` plates are horizontal mirrors of their right-facing
counterparts — from the same sculpt, which is a consistency no second render
could match.

## Provenance, and how to replace the body plates

The **body** plates were cut from a third-party 3D anatomy study sheet that was
already in the media bucket, using
`pipeline/scripts/split_pose_sheet.py` (measured cuts, so the split is
reproducible). They are generic, unbranded and used privately, but they are not
originally ours — if you want a set with no third-party lineage, regenerate them
and keep the filenames:

```bash
# one sheet, then split it into plates with the same script
studio run --model gpt-image-2 --project <project> --slug pose-sheet --no-refs \
  --prompt-file config/pose/prompts/body-sheet.md --dry-run
uv run python pipeline/scripts/split_pose_sheet.py <the sheet> --out config/pose/body
```

The **face** plates are generated from `config/pose/prompts/face-sheet.md` the
same way — no source sheet existed for head orientations.

Because every consumer addresses a plate by filename, swapping the images is a
drop-in: nothing in the spec or the code changes.
