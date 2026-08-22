---
name: studio-media-s3
description: Address studio's media through the studio API — list a folder, upload local files, download to disk, and mint short-lived presigned HTTPS URLs (how images and videos reach Replicate). The canonical asset store for the studio-* workflow, holding CHARACTERS (identity records) and PROJECTS (runs, chains, scenes, movies, input), addressed by NAME PATH and reached with `studio login`; the CLI holds no cloud credentials and knows no bucket name. Use when a task needs to store, fetch, list or hand out large media, to record or address a run, or to cut runs into a scene and scenes into a movie.
---

# studio-media-s3

The asset layer for studio. Files move **disk ↔ store directly** — never
base64-inlined into the agent context — so full-resolution images and multi-MB
videos cost nothing to handle.

The skill is still called `studio-media-s3` and the store is still S3
underneath. You do not address it as S3, and nothing here can.

## Everything goes through the API

`studio` is an API client. It signs in as a user, calls
`studio-api.andreas.services`, and holds **no cloud credentials at all** — reads,
writes, listings and presigned URLs are all API calls. A machine with no cloud
account configured runs the whole pipeline.

```bash
studio login          # prompts for email + password; stores the session
studio whoami         # who you are, and which libraries you can reach
studio logout
```

Sessions refresh themselves; a `401` after that means sign in again.

**There is no bucket name, and never a key you compose.** Material is addressed
by **name path** — `characters/<name>/reference/face/<name>_3.jpg` — which is
the same string a person types and the string every record stores. That it looks
like an object key is a coincidence of how the tree was laid out, and it ends the
first time something is renamed without its bytes moving. Ask for the path you
mean; do not build one out of a prefix.

Bytes still travel straight to storage, not through the API: a presigned URL is
handed back and the transfer happens against it. That is what keeps a video out
of a request-size limit, and it is what makes the rule below hold.

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
    favorites/              an ordinary folder someone made — keepers, copied in
    input/                  the project working pool (<project>_in_<n>.<ext>)

phrasebook/wording.yaml     per-model wording lists     ⟵ SHARED, see below
config/pose/                the reference shoot's framing plates   ⟵ SHARED
```

`<run_id>` is `YYYY-MM-DD_HH-MM-SS_<slug>`, so runs sort chronologically. The
**run owns its output** — medium is an attribute (`result.json`, the file
extension), never a folder name, so one video and ten images take the same shape.
`<scene_id>` and `<movie_id>` take the same shape for the same reason.

**Listings are one folder deep.** There is no prefix scan: a folder is a record
and listing it is a permission-checked read of that record. Walk down to the
folder you mean rather than asking for a subtree.

### The tiers, and the word "shot"

```
generation cut  ⊂  shot  ⊂  scene  ⊂  movie
```

A **generation cut** is a cut *inside* one submission (Kling `multi_prompt`).
A **shot** is one run's output, used as a component of a scene — it was called a
"part", which named its position in a list rather than what it is. A **scene** is
shots stitched into one continuous take. A **movie** is scenes cut together.
(Confusingly, the `studio-media-shot` skill produces a whole still-then-clip chain,
which is usually one shot in this sense. Ask which tier is meant when it matters.)

Scenes and movies are **derived** — the runs they name stay the history, and
either can always be rebuilt.

### A run belongs to a project, and names its characters

`request.json` records `project` (where it lives) and `characters[]` (whose
likeness went into it, inferred from the bindings, not just declared). That list
is what makes "every run using this character" answerable now that the folder no
longer says: `studio runs find --character <name>`.

### THE RULE — the store is the only origin

**Assets are never uploaded to Replicate.** Anything sent to a model must already
be in the store and reaches Replicate only as a short-lived **presigned URL**
minted at submit time. Signed URLs are never *stored* either: run records hold
paths, and the run store refuses a URL-shaped binding. Paths are stable, so any
run replays by re-minting.

## SHARED MATERIAL IS ADDRESSED DIFFERENTLY, AND IT BITES

`phrasebook/wording.yaml` and the `config/pose/` plates belong to **no character
and no project**. Nothing owns them, so nothing records them, so they have **no
catalog record to resolve**. They are reached by key through the API's shared
route instead — still the API, still no credentials, a different door to the same
authority.

**A command that resolves a path fails on them.** `studio download`,
`studio presign` and anything taking `--folder` or `--key` all resolve first and
answer "not found" for both trees. What reaches them is the command that owns
them: `studio phrasebook` for the wording lists, and `studio character shoot`
for the plates.

That failure is quiet where it costs most. A reference shoot binds a pose plate
as its framing guide; a plate that is not there takes the guide with it, and the
render comes back plausible and wrongly framed. If a shoot reports a missing
plate, the plates live in the repo under `studio/config/` and reach the store via
`studio/scripts/dev-setup.sh` — re-run it rather than uploading one by hand.

**`studio phrasebook add` fails the same way and is fixed by the same script.**
Recording a substitution overwrites the wording list and cannot create one, so
against a store that has never held a `wording.yaml` it refuses. The repo ships
a starting copy and `dev-setup.sh` puts it there when the key is absent — and
only then, because after the first `add` the store's copy is the one with the
entries in it. Reading is unaffected either way: no wording list reads as an
empty one, so `terms` and `check` keep working.

## The commands

Every command below is a subcommand of `studio` — `studio --help` for the whole
surface. Model invocation (the registry, the runner, live schema validation)
lives in [`studio-media-core`](../studio-media-core/SKILL.md); this skill is storage.

```bash
# Projects — ASK which one before generating anything; offer to create one
studio projects list
studio projects new <project> --character <name> --description "…"
studio projects show <project>

# List / download / upload / presign, by folder path
studio download --folder characters/<name>/reference --list
studio download --folder characters/<name>/reference --all --dest /tmp/refs --json
studio upload photo.jpg --folder characters/<name>/seed
studio presign --folder characters/<name>/reference/face --json
studio presign --key projects/<project>/runs/<run_id>/output/clip.mp4

# Formats differ between engines: GPT Image writes .webp, Kling takes only
# .jpg/.jpeg/.png. Convert a still before handing it over as a start frame.
# Safe to run unconditionally — an already-accepted image is left untouched.
studio convert --run <project>/latest#1 --for kling --add-input <project>

# Runs: history, chaining, and keepers
studio runs list <project> --character <name>
studio runs show <project>/latest
studio runs outputs <project>/latest --presign    # feed into the next render
studio runs find --character <name>               # across every project

# Frames: verify a clip, and take the handoff frame for chaining
studio frames grid <project>/latest --count 4 --dest /tmp/check
studio frames last <project>/latest --add-input   # -> projects/<p>/input/
studio frames at   <project>/latest --time 6.5

# Chains: a scene's own frames, which are its reference set for later shots
studio frames chain <project>/<slug> --seed projects/<p>/input/<p>_in_<n>.png
studio frames last  <project>/latest --add-input --chain <slug>
studio frames chain <project>/<slug> --args --max 7    # -> --key … --key …

# Phrasebook: per-model wording lists (shared material — see above)
studio phrasebook check --model <model key> --text "<draft prompt>"
studio phrasebook show --model <model key>

# Scenes: a piece planned, shot and cut. `new` starts one from a plan;
# `assemble` does the cutting, and takes runrefs directly when there is no plan.
studio scenes new <project> --slug <slug> --from-json plan.json
studio scenes assemble <project>/<slug> \
  --shot <project>/<run_id>#1 --shot <project>/latest#1
studio scenes list <project>
studio scenes show <project>/latest

# Movies: cut scenes into one piece
studio movies new <project> --slug <slug> \
  --scene <project>/<scene_id> --scene <project>/latest
studio movies show <project>/latest

# Integrity: does every recorded path still resolve?
studio rewrite check
```

`--shot` and `--scene` are repeatable and **order is the cut order**. Each takes
a runref / sceneref, so a chained sequence assembles straight from its own
history. Sources are copied in, so a scene or movie stays playable and
re-stitchable, and the manifest records both the copied path and the originating
ref — copying never loses lineage.

### Runrefs and scenerefs

A run is addressed as `<project>/<run_id>`, `<project>/latest`, a unique slug
fragment, or a bare run id when the project is supplied out of band. Append `#N`
to pick the Nth output (1-based); the default is every output. This is what the
engine skills' `--ref-run` / `--start-run` / `--image-run` flags accept.

A **sceneref** is the same shape one tier up — `<project>/<scene_id>`,
`<project>/latest`, or a unique fragment — and is what `studio movies new --scene`
takes. A scene has exactly one output, so it needs no `#N`.

## Handing assets to Replicate

The store is **private**. To let Replicate fetch an image or video, presign it —
a short-lived HTTPS URL carrying its own signature, signed by the API against
credentials the CLI does not hold. Pass the URLs straight into a prediction's
`reference_images` / `image` inputs. Only short URLs enter the agent context; the
bytes never do. No `REPLICATE_API_TOKEN` is needed for references.

**`--expires` is accepted and ignored, everywhere it appears.** The API owns the
URL's lifetime and sets it centrally; a number passed here cannot be honoured, so
the command says so on stderr rather than pretending. It is comfortably longer
than a render job. The flag survives because the CLI surface is a contract.

## Notes

- **Renaming or moving anything is a record update. No bytes move.** A pool move,
  a regroup, a renumber and a whole character rename are each a handful of row
  edits; the file keeps its bytes and its identity. Use `studio curate` and
  `studio character rename`, which do it.
- **But the records that NAME it still have to be rewritten**, because a record
  stores a path, not an identity. `curate` and `rename` carry them along; that is
  the step whose absence once left 69 records pointing at reference images that
  no longer existed. `studio rewrite check` reports any that remain.
- **Writing to a path that already holds a file replaces it and keeps the
  record**, so everything naming it stays true. Production keeps prior revisions;
  a local dev stack is not the place to rely on that.
- **Listings are natural-sorted** (`<name>_2` before `<name>_10`). Load-bearing,
  not cosmetic: presigned URLs become `[Image1]…[ImageN]` positionally, so a
  lexical order hands a model the wrong image under the right name.
- **Nothing here deletes.** Deleting is a record operation and lives on the
  commands that own the thing; `studio curate` preserves into the destination
  rather than removing. `studio catalog gc` collects blobs no record names, and
  is a dry run without `--apply`.
- Provisioning and teardown live in [`infra/README.md`](../../../infra/README.md).
  Which stack your commands reach — per-machine dev, not production — is in
  [studio/CLAUDE.md](../../../CLAUDE.md).
