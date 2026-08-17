---
name: studio-s3
description: Read from and write to the xharness-prod-media-us-east-1 S3 bucket via the AWS CLI/boto3 — list a prefix, upload local files, download files to disk, and mint short-lived presigned HTTPS URLs (how images/videos reach Replicate). The canonical asset store for the studio-* workflow, holding CHARACTERS (identity records) and PROJECTS (runs, chains, scenes, movies, favorites, input). Use when a skill or task needs to store, fetch, list, or hand out large media assets, to record or address a run, or to cut runs into a scene and scenes into a movie.
---

# S3 skill

The asset layer for xharness. Files move **disk ↔ S3 directly** (never
base64-inlined into the agent context), so it handles full-resolution images and
multi-MB videos cheaply. It replaced the Google Drive layer for the
`studio-*` workflow.

Everything lives in one bucket, **`xharness-prod-media-us-east-1`**, at its
**root** — there is no wrapper prefix. (There was a `media/` one, inherited from
mirroring Google Drive 1:1; it bought nothing and is gone.) Paths passed to
these scripts are full keys, e.g. `characters/<name>/reference`. The bucket is
provisioned by Terraform in [`infra/`](../../../infra/README.md).

Bucket / prefix / region are overridable via env: `XHARNESS_S3_BUCKET`
(default `xharness-prod-media-us-east-1`), `XHARNESS_S3_PREFIX` (default
empty — set it only to stage a copy of the tree elsewhere), `AWS_REGION`
(default `us-east-1`).

## Credentials

No `.env` entry — S3 uses your **AWS CLI login**. Sign in once per session:

```bash
aws login          # or: aws sso login  /  aws configure
```

The scripts resolve whatever the CLI can (the newer `login_session` from
`aws login`, SSO, `credential_process`, or static keys) into boto3 credentials
via `aws configure export-credentials`. This bridge matters because boto3's own
default chain does **not** understand `aws login`. If a script reports it can't
resolve credentials, run `aws login` again (sessions are short-lived).

## The layout

Two trees, because they are two different things. A **character** is an identity
record; a **project** is a piece of work. They used to be one folder, which left
work involving two characters with nowhere to live and work involving none
borrowing a fake character called `misc`.

```
characters/<name>/
    profile.yaml            the bible — identity, plus the described reference index
    reference/              generated character imagery, in purpose subfolders
        face/ body/ wardrobe/ …
    corpus/                 collected material about the character — uploads, keeper clips
    seed/                   the founding real-world source photos
    archive/                retired material; NEVER used unless asked for by name

projects/<project>/
    project.json            name, description, the characters involved
    runs/<run_id>/          one submission: request/prompt/result + output/
    chains/<slug>.json      a scene's own frames, in order — its reference set while building
    scenes/<scene_id>/      runs cut into one continuous take: scene.json + shots/ + output/
    movies/<movie_id>/      scenes cut into one piece: movie.json + scenes/ + output/
    favorites/              keepers, copied out of runs
    input/                  the project working pool (<project>_in_<n>.<ext>)

phrasebook/wording.yaml     per-model wording lists
```

`<run_id>` is `YYYY-MM-DD_HH-MM-SS_<slug>`, so runs sort chronologically. The
**run owns its output** — medium is an attribute (`result.json`, the file
extension), never a folder name, so one video and ten images take the same shape.
`<scene_id>` and `<movie_id>` take the same shape for the same reason.

### The tiers, and the word "shot"

```
generation cut  ⊂  shot  ⊂  scene  ⊂  movie
```

A **generation cut** is a cut *inside* one submission (Kling `multi_prompt`).
A **shot** is one run's output, used as a component of a scene — it was called a
"part", which named its position in a list rather than what it is. A **scene** is
shots stitched into one continuous take. A **movie** is scenes cut together.
(Confusingly, the `studio-shot` skill produces a whole still-then-clip chain,
which is usually one shot in this sense. Ask which tier is meant when it matters.)

Scenes and movies are **derived** — the runs they name stay the history, and
either can always be rebuilt.

### A run belongs to a project, and names its characters

`request.json` records `project` (where it lives) and `characters[]` (whose
likeness went into it, inferred from the bindings, not just declared). That list
is what makes "every run using this character" answerable now that the folder no
longer says: `runs.py find --character <name>`.

### THE RULE — S3 is the only origin

**Assets are never uploaded to Replicate.** Anything sent to a model must already
be an S3 object and reaches Replicate only as a short-lived **presigned URL**
minted at submit time. Signed URLs are never *stored* either: run records hold S3
keys, and `runs.py` refuses a URL-shaped binding. Keys are stable, so any run
replays by re-minting.

## Modules

The code is `studio_pipeline.store`, in the pipeline package at
`studio/pipeline/`, and every command below is a subcommand of `studio` — run
`studio --help` for the whole surface. `s3.py` (auth/helpers) and `paths.py` are
libraries, not commands. Model invocation — the registry, the runner, live
schema validation — lives in [`studio-core`](../studio-core/SKILL.md); this
skill is storage.

| Script | Purpose |
|---|---|
| `paths.py` (lib) | **The one module that knows the tree's shape.** Every key in the harness is built here; `s3_common.key()` stays the single place a global prefix is applied. Library, not a CLI. |
| `projects.py` | Project CRUD (`list`/`new`/`init`/`show`) and the project **input pool** (`add-inputs`/`inputs`). `require_project()` is what turns a missing `--project` into an error that lists the real options. |
| `runs.py` | The shared **run store** every studio-* engine records into: request/prompt/result, output archiving, runref resolution for chaining, `find --character` across projects, and `favorite`. Library + CLI. |
| `scenes.py` | The **scene store**: an ordered list of run outputs stitched into one continuous video under `projects/<p>/scenes/<scene_id>/`, as `shots/`. |
| `movies.py` | The **movie store**: scenes cut into one piece under `projects/<p>/movies/<movie_id>/`. Same shape one tier up. |
| `video.py` | The shared ffmpeg layer — probe, stitch, frame grab, contact grid. A scene and a movie join their inputs by identical rules because they call the same function. ffmpeg ships in the wheel; no system install. |
| `frames.py` | Stills out of a run's video: `last` (the chaining handoff — a clip's final frame, straight into the project's input pool), `grid` (a contact sheet, so a clip can be *looked at* before more money is spent on top of it), and `chain` (the frames a scene has produced, which are **its** reference set for later shots — not a character's). |
| `rewrite.py` | **When an object moves, the records that name it must follow.** `apply_moves()` is what `curate.py` and the migrator call; `check` walks every record and confirms what it names still exists. Run it after any manual S3 surgery. |
| `phrasebook.py` | Per-model **wording lists** — a phrase, and the phrase to use instead. Models read the same idea differently. Kept as data in S3 (`phrasebook/wording.yaml`), like characters. |
| `s3_upload.py` | Upload local file(s) under a key prefix. Prints `s3://` URIs; `--presign` also prints HTTPS URLs. |
| `s3_download.py` | List a folder (`--list`), download everything (`--all`) or named files to a dir. |
| `s3_presign.py` | Mint temporary HTTPS GET URLs — **how assets reach Replicate**. |
| `s3_convert.py` | Re-encode an image so a target model accepts it (`--for <model key>`), writing the result into the project's input pool. The source is never modified. |
| `backfill_replicate.py` | One-shot import of historical Replicate predictions into the run store (`--since DATE`, `--dry-run`, idempotent). |
| `migrate_layout.py` | The one-off move from the pre-restructure `media/<owner>/…` tree. Kept for the record and for any bucket that still holds an old tree. |

```bash

# Projects — ASK which one before generating anything; offer to create one
studio projects list
studio projects new <project> --character <name> --description "…"
studio projects show <project>

# List / download / upload / presign, by key prefix
studio download --folder characters/<name>/reference --list
studio download --folder characters/<name>/reference --all --dest /tmp/refs --json
studio upload --folder characters/<name>/seed photo.jpg
studio presign --folder characters/<name>/reference/face --json

# Formats differ between engines: GPT Image writes .webp, Kling takes only
# .jpg/.jpeg/.png. Convert a still before handing it over as a start frame.
# Safe to run unconditionally — an already-accepted image is left untouched.
studio convert --run <project>/latest#1 --for kling --add-input <project>

# Runs: history, chaining, and keepers
studio runs list <project> [--character <name>]
studio runs show <project>/latest
studio runs outputs <project>/latest --presign    # feed into the next render
studio runs find --character <name>               # across every project
studio runs favorite <project>/latest#1

# Frames: verify a clip, and take the handoff frame for chaining
studio frames grid <project>/latest --count 4 --dest /tmp/check
studio frames last <project>/latest --add-input   # -> projects/<p>/input/
studio frames at   <project>/latest --time 6.5

# Chains: a scene's own frames, which are its reference set for later shots
studio frames chain <project>/<slug> --seed projects/<p>/input/<p>_in_<n>.png
studio frames last  <project>/latest --add-input --chain <slug>
studio frames chain <project>/<slug> --args --max 7    # -> --key … --key …

# Phrasebook: per-model wording lists (data lives in S3)
studio phrasebook check --model <model key> --text "<draft prompt>"
studio phrasebook show --model <model key>

# Scenes: cut a sequence of runs into one continuous take
studio scenes new <project> --slug <slug> \
  --shot <project>/<run_id>#1 --shot <project>/<run_id>#1 --shot <project>/latest#1
studio scenes list <project>
studio scenes show <project>/latest

# Movies: cut scenes into one piece
studio movies new <project> --slug <slug> \
  --scene <project>/<scene_id> --scene <project>/latest
studio movies show <project>/latest

# Integrity: does every recorded key still resolve?
studio rewrite check
```

`--shot` and `--scene` are repeatable and **order is the cut order**. Each takes
a runref / sceneref, so a chained sequence assembles straight from its own
history. Sources are copied in server-side, so a scene or movie stays playable
and re-stitchable, and the manifest records both the copied key and the
originating ref — copying never loses lineage.

### Runrefs and scenerefs

A run is addressed as `<project>/<run_id>`, `<project>/latest`, a unique slug
fragment, or a bare run id when the project is supplied out of band. Append `#N`
to pick the Nth output (1-based); the default is every output. This is what the
engine skills' `--ref-run` / `--start-run` / `--image-run` flags accept.

A **sceneref** is the same shape one tier up — `<project>/<scene_id>`,
`<project>/latest`, or a unique fragment — and is what `movies.py --scene`
takes. A scene has exactly one output, so it needs no `#N`.

## Handing assets to Replicate

The bucket is **private**. To let Replicate fetch an image or video, presign it —
a short-lived (default 1 h) HTTPS URL that carries its own signature. Pass the
resulting URLs straight into a prediction's `reference_images` / `image` inputs.
Only short URLs enter the agent context; the bytes never do. This replaces the
old Drive→local→Replicate-Files-upload dance — no `REPLICATE_API_TOKEN` needed
for references.

## Notes

- Uploads overwrite a same-named key; the bucket is **versioned**, so the prior
  revision is retained (mirrors Drive's update-in-place-with-history).
- `list_keys` skips zero-byte folder markers and natural-sorts (`<name>_2`
  before `<name>_10`).
- Moving an object means rewriting the records that name it. Use `curate.py`
  (which does) rather than `aws s3 mv` (which does not), and run
  `rewrite.py check` if you ever move something by hand.
- Provisioning, teardown, and the presigned-URL cheatsheet live in
  [`infra/README.md`](../../../infra/README.md).
