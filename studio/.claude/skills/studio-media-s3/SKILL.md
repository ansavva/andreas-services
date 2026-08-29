---
name: studio-media-s3
description: Address studio's media through the studio API — list a folder, upload local files, download to disk, and mint short-lived presigned HTTPS URLs (how images and videos reach Replicate). The canonical asset store for the studio-* workflow, holding CHARACTERS (identity records) and PROJECTS (runs, chains, scenes, movies, input), addressed by NAME PATH and reached with `studio login` against a named profile (dev or prod); the CLI holds no cloud credentials and knows no bucket name. Use when a task needs to store, fetch, list or hand out large media, to record or address a run, or to cut runs into a scene and scenes into a movie.
---

# studio-media-s3

The asset layer for studio. Files move **disk ↔ store directly** — never
base64-inlined into the agent context — so full-resolution images and multi-MB
videos cost nothing to handle.

The skill is still called `studio-media-s3` and the store is still S3
underneath. You do not address it as S3, and nothing here can.

## Everything goes through the API

`studio` is an API client. It signs in as a user, calls a studio API, and holds
**no cloud credentials at all** — reads, writes, listings and presigned URLs are
all API calls. A machine with no cloud account configured runs the whole
pipeline.

```bash
studio login          # prompts for email + password; stores the session
studio whoami         # profile, who you are, and which libraries you can reach
studio logout
```

Sessions refresh themselves; a `401` after that means sign in again.

**Which API, and which library, is the PROFILE.** `dev` is the default and means
this machine's own stack; `prod` means the deployed library, with real material
and real money behind it. Sessions are per-profile, so signing in to one does
not sign you out of the other.

```bash
studio profile list                  # what exists, and which is in force
studio profile show                  # what each value resolves to, and from where
studio --profile prod runs list      # one invocation against the deployed library
```

**Check `studio whoami` before writing anything you would not want in the live
library.** It prints the profile first, for that reason.

**There is no bucket name, and never a key you compose.** Material is addressed
by **node id**, or by the **name path** that resolves to one —
`<name>/reference/face/<file>` is the string a person types. It is an *address*,
resolved against the tree as it is now; it is not a key, and no record stores
one. The S3 key behind it is built from ids and is meaningless to everything
outside the API. Ask for the path you mean; do not build one out of a prefix.

Bytes still travel straight to storage, not through the API: a presigned URL is
handed back and the transfer happens against it. That is what keeps a video out
of a request-size limit, and it is what makes the rule below hold.

## The layout

**Characters and projects are records, and each owns a folder.** A character is
an identity; a project is a piece of work. Both folders sit directly under the
library root — there is no `characters/` or `projects/` wrapper, because an
entity is found by asking for it, not by listing a folder that groups it.

```
<name>/                     a character's folder
    reference/              the images its references point at, in purpose
        face/ body/ wardrobe/ …     subfolders
    corpus/                 collected material — uploads, keeper clips
    seed/                   the founding real-world source photos
    archive/                retired material; NEVER used unless asked for by name

<project>/                  a project's folder
    runs/<run_id>/          one submission: its payload documents + output/
    chains/<slug>.json      a scene's own frames, in order
    scenes/<scene_id>/      runs cut into one continuous take: storyboard/ shots/ output/
    movies/<movie_id>/      scenes cut into one piece: scenes/ + output/
    input/                  the project working pool

config/angle/                the turnaround's framing angle images
```

**The documents that used to define these things are gone.** No `profile.yaml`,
no `project.json`, no `scene.json`, no `movie.json` — each is a row, so each can
be queried, and none can drift from the folder it used to sit in. A run keeps
`request.json` and `result.json`, but as *payload*: the provider's own bytes,
stored and never decoded.

**Every folder name here is convention.** The API makes them with the entity and
resolves them by name when it needs one, creating what is absent. Rename `runs/`
and the next run makes a new one; existing runs stay reachable because each names
its own folder node.

`<run_id>` is `YYYY-MM-DD_HH-MM-SS_<slug>`, so runs sort chronologically when
browsed — it is a name, not an id. The **run owns its output** — medium is an
attribute, never a folder name, so one video and ten images take the same shape.

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
minted at submit time. Signed URLs are never *stored* either: a run's bindings
are **node ids**, and both the run store and the API refuse a URL-shaped one.
Ids are stable, so any run replays by re-minting.

## SHARED MATERIAL, AND THE TRAP THAT USED TO BE HERE

The the `config/angle/` images belong to **no character and no project** — they are
the library's, and the repo is their source of truth.

**They are ordinary nodes, and that is the change.** They had no catalog record
for as long as nothing owned them, so they were reached by raw key through a
separate route, and every command that resolved a path answered "not found" for
them. That was quiet where it cost most: a turnaround binds an angle image as
its framing guide, and an angle image the turnaround could not see took the guide with it
and returned a render that was plausible and wrongly framed. They resolve like
anything else now, and `studio download`, `studio presign` and `--folder` all
work on them.

If a turnaround still reports a missing angle image, the angle images live in the repo under
`studio/config/` and reach the store via `studio/scripts/dev-setup.sh` — re-run
it rather than uploading one by hand.

The phrasebook used to be named here too. It is `TERM#` rows now, so there is no
document to address and `studio phrasebook` is the whole of its surface.

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
studio download --folder <name>/reference --list
studio download --folder <name>/reference --all --dest /tmp/refs --json
studio upload photo.jpg --folder <name>/seed
studio presign --folder <name>/reference/face --json

# Cut a rectangle out of an image already in the tree. The source is untouched.
studio crop --key <node> --box 120,40,880,1400 --add-input <project>
studio presign --key <project>/runs/<run_id>/output/clip.mp4

# Formats differ between engines: GPT Image writes .webp, Kling takes only
# .jpg/.jpeg/.png. Convert a still before handing it over as a start frame.
# Safe to run unconditionally — an already-accepted image is left untouched.
studio convert --run <project>/latest#1 --for kling --add-input <project>

# Runs: history, chaining, and keepers
studio runs list <project> --character <name>
studio runs show <project>/latest
studio runs outputs <project>/latest --presign    # feed into the next render
studio runs find --character <name>               # across every project
studio runs edit <project>/latest                 # a DRAFT's prompt, params and images
                                                  # — withdraws any approval
studio runs delete <project>/latest              # keeps the folder; --files delete removes it

# Frames: verify a clip, and take the handoff frame for chaining
studio frames grid <project>/latest --count 4 --dest /tmp/check
studio frames last <project>/latest --add-input   # -> <project>/input/
studio frames at   <project>/latest --time 6.5

# Chains: a scene's own frames, which are its reference set for later shots
studio frames chain <project>/<slug> --seed <project>/input/<file>.png
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

- **Renaming or moving anything is a record update. No bytes move.** A pool
  move, a regroup and a whole character rename are each a handful of row edits;
  the file keeps its bytes and its identity. Use `studio curate` and
  `studio character rename`, which do it.
- **And nothing that names it has to be rewritten.** A record stores a node id,
  which is the file's identity rather than its address, so a rename or a move
  strands nothing. This is the one entry here that reversed: a record used to
  store a path, and carrying those along was a step whose absence once left 69
  records pointing at reference images that no longer existed. There is no
  `rewrite` command any more because there is no longer anything for it to find.
- **Writing to a path that already holds a file replaces it and keeps the
  record**, so everything naming it stays true. Production keeps prior revisions;
  a local dev stack is not the place to rely on that.
- **Every file carries a `checksum`** — the MD5 of its bytes, recorded when the
  upload is confirmed. Two files with the same one are byte-identical, which is
  what `studio curate dedupe` compares instead of downloading anything.
- **Listings are natural-sorted** (`<name>_2` before `<name>_10`). Load-bearing,
  not cosmetic: presigned URLs become `[Image1]…[ImageN]` positionally, so a
  lexical order hands a model the wrong image under the right name.
- **Nothing here deletes.** Deleting is a record operation and lives on the
  commands that own the thing — `studio runs delete`, `studio projects delete`;
  `studio curate` preserves into the destination rather than removing. Both keep
  the folder unless asked with `--files delete`, because the reverse default
  loses generated media to a typo. **Bytes a delete strands are the API's
  problem, not yours** — it records what it is about to free before it frees it,
  and the next delete finishes anything an interrupted one left. There used to be
  a command for sweeping those up by hand; there is nothing to run.
- Provisioning and teardown live in [`infra/README.md`](../../../infra/README.md).
  Which stack your commands reach — per-machine dev, not production — is in
  [studio/CLAUDE.md](../../../CLAUDE.md).


## Framing an image: `studio crop`

**The box is `LEFT,TOP,RIGHT,BOTTOM` in source pixels** — the same order a
detector reports and Pillow takes, and deliberately not `LEFT,TOP,WIDTH,HEIGHT`.
A box that runs off an edge is clamped rather than refused, because padding a
detection produces one routinely; a box that misses the image entirely is
refused, because that is a mistake rather than a rounding.

```bash
studio crop --key <node> --box 120,40,880,1400 --add-input <project>
studio crop --run <project>/latest#1 --box 0,0,1179,2196 --to jpg \
    --dest-key characters/<name>/seed/current/<file>.jpg
```

**It does not find the subject, and will not.** Face and body detection are
platform work and a wrong box is worse than no command — detect however you
like, then state the box here. What this buys over cropping on a laptop is that
the cut is recorded, repeatable and applied to the object the library holds
rather than to a copy that has drifted.

## Two things that used to bite

**`upload` creates its destination.** It did not, so the first file into a new
subfolder died on a parent that did not exist, and nothing in the CLI created
one — organising a pool into subfolders was a dead end reached through a
dry-run `curate dedupe --group <name>` run for its side effect. Missing
ancestors are created too.

**Prefer node ids in anything scripted.** A name is unique only within one
folder, and pools are trees: after a library is organised, `IMG_4549__crop.jpg`
can legitimately exist in `seed/current/`, `seed/earlier/` and `archive/crops/`
at once. Commands that take a file accept `<group>/<name>` to disambiguate and
refuse an ambiguous bare name rather than guessing — which is right, and is
also a batch of 29 moves failing at once if a script assumed basenames were
unique. `--json` prints ids next to names for exactly this.
