# studio — the generation pipeline

The local half of studio: the Claude Code skills that produce the media, and
the rules that govern them. For the deployed browser over the output, see
[WEB_APP.md](WEB_APP.md); for the map of both, [../CLAUDE.md](../CLAUDE.md).

Nothing here deploys. These skills run inside Claude on your own machine, under
your own AWS login, and reach the same bucket the app reads. Skills live in
`studio/.claude/skills/`, in two families: **`studio-media-*`** for using the
pipeline to make media, **`studio-code-*`** for working on the pipeline's own
code. The code is one package with one dependency set — see [Layout](#layout).

---

## Hard rules

These are not preferences. They hold everywhere in this repo, in every skill,
and in anything written back to it.

### 1. NEVER name a character anywhere in the repo

**No character name appears in this repository — ever.** Not in code, docstrings,
`SKILL.md` files, examples, comments, tests, fixtures, commit messages, branch
names, or pull request titles and bodies.

Characters are **data, not code**: they live only in S3 under `characters/<name>/`
(see `studio-media-character`). The repo describes the *machinery* that operates on any
character, so it never needs to know one by name.

Use the placeholder `<name>` in every example and help string:

```bash
studio run --model nano-banana-pro --project <project> \
  --prompt "..." --character <name>
studio runs outputs <project>/latest --presign
```

The same goes for **project** names: a project is usually named after the work,
but today's are named after characters, so use `<project>` in examples too.

The same goes for anything that identifies a character indirectly — a scene, a
catchphrase, or a distinctive slug. Prefer `<slug>` over a real one. When writing
a commit message or PR about character work, describe the change to the tooling,
not the character it was done for.

### 2. NEVER submit without approval of the FULL payload

**Show the user the complete `input` object as JSON — every parameter, not just
the prompt — and wait for them to say yes before any prediction is created.**
Every submission bills, and a wrong `duration` or `mode` costs exactly as much as
a wrong prompt. Re-approve after *any* edit — an approval covers the payload that
was shown, not the next revision of it.

**Different models take different inputs.** Seedance takes `image` /
`last_frame_image` / `seed` / `resolution`; Kling takes `start_image` /
`end_image` / `mode` / `multi_prompt` and has no seed at all. Never assume a
field carries over between them. Every model's inputs, caps and caveats live in
the **registry** (`engine/models.json`), and the runner fetches the
target model's **live input schema** to reject unknown fields, bad enums and
out-of-range numbers — plus documented constraints the schema does not enforce —
before anything bills. Review the payload, then let the validator confirm the
model actually accepts it.

**Show it as TWO JSON documents — never one.** A single document is unreviewable:
`prompt` is often itself a serialized JSON object, so nesting it double-escapes
onto one enormous line. Split, both stay readable, and it mirrors how a run is
stored (`prompt.json` beside `request.json`):

```
===== 1/2  PROMPT — serialized into the `prompt` string at submit time =====
{ …the prompt as real, indented JSON (or the plain string, for image prompts)… }

===== 2/2  INPUT — the parameters this model receives =====
{ "run": …, "model": …, "endpoint": …, "input": { "prompt": "<< see 1/2 >>", … } }
```

`--dry-run` renders exactly this for every model (`runs.py: render_payload()`);
`--dry-run --json` emits the raw payload plus its `bindings` for machines. Image inputs appear
as `<presigned: characters/… | projects/…>` — the S3 key that will be signed into that field at
submit time, since the signed URL itself is ~2 KB of noise and expires.

The gate covers what is sent to the model. The surrounding steps — presigning,
polling, downloads, uploads, recording the run — do not need approval.

**Approval is of a payload, not of a plan.** A yes to "shall I render this?", an
answer to a multiple-choice question, or a payload shown earlier in the
conversation is not approval of the request about to be sent. Show it again and
wait. There is deliberately no `--yes`-style flag on any generating command: an
approval flag is precisely the door an agent walks through while believing some
earlier exchange counted as consent. If one reappears, it is a bug.

### 2b. NEVER put an image into a character without approval

Runs are append-only history and descriptions can be rewritten, but
`characters/<name>/reference/` is **who the character is** — every later render is
verified against it, and every future generation may be driven by it. Adding,
replacing, renumbering or archiving anything there, or in `default_set` or the
bible's `references:` index, is a decision that belongs to the user and is
**separate** from having agreed to spend money on a render.

So a successful generation does not become identity by itself.
`studio character shoot` leaves every result in its run and prints the promotion
line; a person looks, and then:

```bash
studio runs outputs <project>/latest --presign            # look first
studio character add-refs <name> --to <group> --from-run <runref>
```

`add-refs` copies inside the bucket, so the run keeps its own output and no
record ends up naming a key that moved.

Both this rule and the one above were broken in a single session — a shoot
submitted on the strength of a menu answer, and its output then written into a
character's face group that nobody had approved. Nothing was overwritten, but
nothing about that was safe by design; it was safe by luck of the numbering.

### 3. S3 is the only origin

**Assets are NEVER uploaded to Replicate.** Everything sent to a model must
already be an S3 object, reaching Replicate only as a short-lived presigned URL
minted at submit time — and signed URLs are never stored. Full detail under
[asset storage](#asset-storage) below; enforced in code by `runs.py`.

---

## Layout

The pipeline is **one package** with **one command**. The `SKILL.md` files are
its agent-facing documentation and hold no code.

```
studio/pipeline/
├── pyproject.toml  uv.lock        one dependency set, one console script
├── tests/                         moto-backed; needs no AWS
└── src/                           ← src layout, deliberately (see below)
    └── studio_pipeline/
        ├── cli.py                 `studio` — the root group, wiring only
        ├── errors.py              domain failure -> `error: …` and exit 1
        ├── __init__.py            STUDIO_DIR, ENV_FILE, env_value
        │
        ├── adapters/              THE OUTSIDE WORLD — everything with a side effect
        │   ├── s3.py              credentials bridge, BUCKET/PREFIX/REGION
        │   ├── replicate.py       the HTTP client
        │   └── ffmpeg.py          probe / stitch / grab
        │
        ├── domain/                WHAT THINGS ARE — records and the tree's shape
        │   ├── paths.py           the one module that knows the key layout
        │   ├── runs.py  scenes.py  storyboard.py  movies.py  frames.py
        │   ├── projects.py
        │   ├── characters.py  curate.py  contact_sheet.py
        │   ├── phrasebook.py  rewrite.py  prompt.py
        │   └── templates/profile.yaml  reference_shots.yaml
        │
        ├── engine/                MODEL INVOCATION
        │   ├── models.json        the REGISTRY — models are data, not code
        │   ├── runner.py          `studio run` / `studio models`
        │   ├── shoot.py           `studio character shoot` — the standard set
        │   ├── board.py           `studio scenes board` / `render` / `check`
        │   ├── registry.py  schema.py  submit.py  refs.py  add_model.py
        │
        ├── objects/               raw object access
        │   └── upload.py  download.py  presign.py  convert.py
        │
        └── maintenance/           one-shots, quarantined
            └── backfill_replicate.py  migrate_layout.py
```

**Why the directories are named after what things ARE.** They used to be one
`store/` holding six unrelated kinds of thing — an S3 adapter, the key layout,
the record stores, an ffmpeg wrapper, four thin CLI verbs and two one-shot
migrations. "Store" described where bytes live, which was true of `s3.py` and
meaningless for a module that shells out to ffmpeg. Dependencies now point one
way: `cli` → `domain` → `adapters`.

**Why `src/`.** Without it, Python puts the working directory first on the
import path, so tests can pass against files that were never packaged. Both
`models.json` and `profile.yaml` are package data reached at runtime; a wheel
missing either fails only when someone runs the command. `src/` forces the
tests to exercise the installed package.

**One constant knows where `studio/` is**: `studio_pipeline.STUDIO_DIR`. It
searches upward for the directory holding both `backend/` and `pipeline/`
rather than counting `".."` segments — a count is right only for one file's
depth, and moving the package to `src/` proved that by breaking it.

---

## One-time setup

```bash
studio/scripts/dev-setup.sh
```

This installs the only hard prerequisite — `uv` — via `brew install uv` if it's
missing, syncs the pipeline package, and puts its `studio` command on PATH for
the session. Idempotent, so it's safe to run any time.

It runs automatically at the start of every Claude Code session, from the repo's
`SessionStart` hook (`.claude/hooks/session-start.sh` at the monorepo root),
so a fresh session comes up ready to use. That hook is shared with the rest of
the monorepo — studio's setup is one guarded, non-fatal step inside it.

External tools:
- **AWS CLI** (`aws`) — `brew install awscli` — **required**. It is how the
  pipeline reaches the bucket: `store/s3.py` bridges `aws configure
  export-credentials` into boto3, because boto3's own chain does not understand
  an `aws login` session. Sign in with `aws login` each session.
- **ffmpeg** — `brew install ffmpeg` — optional. The scene and movie code
  vendors `imageio-ffmpeg`; this is for checking a render by hand.

API keys:
- **REPLICATE_API_TOKEN** — https://replicate.com/account/api-tokens —
  **required**. Every engine runs on Replicate: `bytedance/seedance-2.0`,
  `kwaivgi/kling-v3-omni-video`, `google/nano-banana-pro`,
  `google/nano-banana-2`, `openai/gpt-image-2`, `openai/gpt-image-1.5`.
  Put it in `studio/.env` (copy `studio/.env.example`; `.env` is git-ignored).

Asset storage uses your **AWS login**, not an API key. Character profiles,
reference images and every generated asset live in S3 (bucket
`studio-prod-media-us-east-1`), never in git — see
[`../infra/README.md`](../infra/README.md).

### The two trees — characters and projects

A **character** is an identity record. A **project** is a piece of work. They
used to be one folder, which left work involving two characters with nowhere to
live and work involving none borrowing a fake character called `misc`.

```
characters/<name>/
    profile.yaml    the bible — identity, plus the DESCRIBED reference index
    reference/      generated character imagery, in purpose subfolders
        face/  body/  wardrobe/  frame/ …
    corpus/         collected material about the character — uploads, keeper clips
    seed/           the founding real-world source photos
    archive/        retired material — NEVER used unless the user names it

projects/<project>/
    project.json    name, description, the characters involved
    runs/           one directory per submission
    chains/         an ad-hoc sequence's frames (a planned scene derives its own)
    scenes/         runs cut into one continuous take
    movies/         scenes cut into one piece
    favorites/      an ordinary folder someone made — the tools do not write here
    input/          the project working pool (<project>_in_<n>.<ext>)

phrasebook/wording.yaml

config/pose/body/*.png       pose plates — how to stand, for a reference shoot
config/pose/face/*.png       head-angle plates
```

There is **no `media/` prefix** — the tree is at the bucket root. (There was one,
inherited from mirroring Google Drive 1:1; it bought nothing.)

**`config/` is the one tree whose source of truth is the repo.** It lives at
`studio/config/`, and `dev-setup.sh` syncs it out (`--size-only`, never
`--delete`). The bucket holds a copy because a model may only be handed a
presigned URL of an S3 object — a plate that was never synced cannot be used, so
`shoot` checks for them and says to re-run the script. Editing a plate in the
bucket rather than the repo is how they diverge.

It also has to be listed in `KEY_ROOTS` (`domain/runs.py`): a binding outside the
known roots is refused when the request is recorded, which is what stops a typo
or a URL from reaching a stored record.

**Ask which project before generating anything.** `--project` is required and
never inferred: where output lands is the one thing rerunning a command cannot
undo. Offer the existing projects (`projects.py list`) and the option of a new
one (`projects.py new`), and settle it *before* showing a payload for approval —
approving a payload must never imply approving where it lands.

### The tiers — run, shot, scene, movie

```
generation cut  ⊂  shot  ⊂  scene  ⊂  movie
```

A **generation cut** is a cut inside one submission (Kling `multi_prompt`). A
**shot** is one run's output used as a scene component — it was called a "part",
which named its position in a list rather than what it is. A **scene** is shots
stitched into one continuous take. A **movie** is scenes cut together.
(Separately, the `studio-media-shot` skill produces a whole still-then-clip chain,
usually one shot in this sense.)

Every submission to Replicate, from any `studio-*` engine, is recorded as a
**run**:

```
projects/<project>/runs/<YYYY-MM-DD_HH-MM-SS>_<slug>/
    request.json    what we sent — references as S3 KEYS, plus `characters[]`
    prompt.json     the studio-media-prompt source, when one was used
    result.json     prediction id, status, media types, output keys
    output/         the artifact(s) — .mp4, .jpg, however many
```

A run belongs to a project and **names the characters it used**, inferred from
its bindings rather than trusted from the flags. That list is what makes "every
run using this character" answerable now that the folder no longer says it:
`runs.py find --character <name>`.

A **scene is keyed by its slug** and created before anything renders — it is
the plan as much as the record. A **movie** still takes the run id shape,
because a movie is only ever a finished cut:

```
projects/<project>/scenes/<slug>/
    scene.json      the plan AND the record — shots, panels, runs, the cut
    storyboard/     the panels: shot-<NN>-p<M>.png
    shots/          each source clip, copied in, numbered in cut order
    output/         the stitched scene — <slug>.mp4

projects/<project>/movies/<YYYY-MM-DD_HH-MM-SS>_<slug>/
    movie.json      the manifest — scenes in cut order, as SCENEREFS and S3 KEYS
    scenes/         each scene's output, copied in, numbered in cut order
    output/         the finished movie — <slug>.mp4
```

Both are **derived, never a source of truth**: the runs they name remain the
history, so either can always be rebuilt. Sources are copied in server-side so a
scene stays playable as its runs accumulate around it, and each manifest records
the originating ref beside the copied key — copying does not lose lineage. Both
stitch through the same `s3/scripts/video.py`, which stream-copies when the
inputs already agree on codec, geometry, frame rate and audio layout, and
re-encodes (recording that it did) when they don't.

### Identity vs working material — never conflate them

`characters/<name>/reference/` is a **library** of generated character imagery,
organised in purpose subfolders and **described in the bible** (`references:`).
The engines cap what they accept (Kling 7, Seedance 9, Nano Banana 14) and send
it in full, so a *subset* is chosen deliberately — `--pick`, `--pick-tag`, or
the character's `default_set`. An over-cap selection is **refused**, with the
index printed, rather than truncated: which images a generation saw should not be
decided by whatever a folder listing returned.

`projects/<project>/input/` is the **working pool** — uploads and frames pulled
off clips to drive the next generation. Uncapped, picked from by number
(`--input N`), never identity.

**A frame pulled off a run goes to the project pool.** Promoting one into a
character's `reference/` feeds model output back in as identity and compounds
drift; it is a deliberate curation decision, and it should be described when it
happens.

**Moving an object means rewriting the records that name it.** Run records,
scene and movie manifests and chains all store S3 keys, so a move invalidates
every document that cited it. `curate.py` does that rewrite in the same
operation; `rewrite.py check` reports anything left dangling. Curating without
that step is what left 69 records pointing at reference images that no longer
existed.

The **run owns its output**; medium is an attribute, never a folder name, so one
video and ten images take the same shape. `runs/` is **append-only history**.
Runs chain: one run's output feeds the next as a start frame (`--start-run`) or
as reference material (`--ref-run`), addressed by **runref**
(`<project>/latest#1`).

### THE RULE — S3 is the only origin

**Assets are NEVER uploaded to Replicate.** Anything sent to a model must already
be an S3 object, and reaches Replicate only as a short-lived **presigned URL**
minted at submit time. Signed URLs are never *stored* either — run records hold
S3 keys, because URLs expire, are ~2 KB of noise each, and carry time-limited
bucket access that must not outlive the request. `runs.py` refuses a URL-shaped
binding, so this is enforced in code. To use a local file, upload it to S3 first.

---

## Available skills

All fifteen live in `studio/.claude/skills/` and are discovered as
`studio:<name>` — directory-scoped, so they surface when the work is under
`studio/`. The `[studio-*]` marker below is historical; every skill here is
part of the pipeline now.

| Skill     | What it does                                              |
|-----------|-----------------------------------------------------------|
| `studio-media-scene`     | **A piece longer than one generation.** Chains video runs — each starting from the previous clip's last frame — then stitches them into one cut. Owns the chain loop, the continuity rules that keep shots cutting together, the per-shot verification gate, and the `multi_prompt`-cuts-vs-timing trade. Use when a shot outruns the model's duration ceiling or must read as one continuous take |
| `studio-media-movie`     | **The tier above a scene.** Cuts a project's finished scenes into one piece. Owns the cut order and the movie-vs-longer-scene decision: cut a movie where a hard cut belongs (a change of place, time or subject); extend a scene where it must read as one take |
| `studio-media-shot`      | **Orchestrates a whole shot**: reads a brief, shows the multi-step plan as JSON for approval, then renders a still and animates it — frame-first, one approval gate per billing step. Use when a brief describes motion or spans more than one studio-* call |
| `studio-media-core`      | **The shared machinery.** The model **registry** (`models.json`), the one submit lifecycle, live-schema validation, and `studio run` — the runner that invokes *any* registered model. Models are DATA, not code |
| `studio-media-add-model` | **Onboard a new Replicate model**: reads its live schema *and* its README, proposes a registry entry for review, then writes it to the registry. Also owns writing the new model's skill page — nothing generates it. The only way a model should be added |
| `studio-media-image`     | The **frame-first workflow** for stills — why to render a frame before a video, run chaining, the approval gate, choosing between the image models. Model-agnostic; each model has its own skill |
| `studio-media-nano-banana-pro` | `google/nano-banana-pro` — strongest all-round image model, the usual default for character frames. Legible text, 4K, ≤14 refs, tunable safety filter. **Never set `allow_fallback_model`** — it reroutes to a different model than the one approved |
| `studio-media-nano-banana-2` | `google/nano-banana-2` — fast/cheap sibling. The only model with the extreme `1:4`…`8:1` ratios; Google Search / Image Search grounding |
| `studio-media-gpt-image-2` | `openai/gpt-image-2` — OpenAI's newest. Dense legible text, pixel-exact sizes, references held at high fidelity **automatically**. No transparent background |
| `studio-media-gpt-image-1-5` | `openai/gpt-image-1.5` — the one that does **transparent backgrounds** and exposes `input_fidelity` (dial face preservation up *or down*). Aspect limited to `1:1`/`3:2`/`2:3` |
| `studio-media-seedance`  | `bytedance/seedance-2.0` — native audio, first/last frame, reference images/videos/audio. A start frame and a reference set **cannot** be combined |
| `studio-media-kling`     | `kwaivgi/kling-v3-omni-video` — Kling 3.0 / O3 Omni (~$0.168/s, `reference_images` for consistency, native multi-shot to 6 cuts). Start frame and reference images can be combined |
| `studio-media-prompt`    | Author prompts as structured JSON for either engine (`--engine seedance\|kling-replicate`); validates rules and routes technical fields + the negative prompt where each engine takes them |
| `studio-media-character` | Manage on-model characters (create/update/list/curate/load) whose bible + described reference library live in S3 (`characters/<name>/`); characters are data, not skills |
| `studio-media-s3`               | Read/write the `studio-prod-media-us-east-1` S3 bucket (list, upload, download, presign) — the asset store holding **characters** and **projects**, plus the shared **run store** (`runs.py`), **scene store** (`scenes.py`) and **movie store** (`movies.py`), the project registry (`projects.py`), the layout module (`paths.py`) and the record rewriter (`rewrite.py`). Storage only; model invocation lives in `studio-media-core` |

---
## How the code is invoked

Everything is a subcommand of one console script:

```bash
studio --help              # the whole surface, grouped
studio runs --help         # a command's own options
```

```bash
cd studio/pipeline && uv run pytest tests/ -q
```

`scripts/dev-setup.sh` installs the package and puts `studio` on PATH; the
repo's `SessionStart` hook runs it, so a fresh session has the command already.
To run it without that: `uv run --project studio/pipeline studio …`.

Note two commands that read alike and are not:

```
studio run      submit a generation   (creates a run)
studio runs     query the run store   (reads the runs)
```

This replaced nineteen standalone scripts, each with its own argparse parser,
its own PEP 723 dependency block and its own `uv run <path>` invocation. The
per-script dependency isolation was buying nothing — the union across all of
them was four packages, and every script wanted `boto3` plus at most one other —
while costing a resolve per script, no shared lockfile, and cross-module calls
that had to shell out through `uv run` because no two scripts shared an
interpreter. Those calls are now ordinary function calls.

The parsing is **Click**, and the port was mechanical on purpose:
`pipeline/tests/cli_surface_reference.json` records what argparse exposed —
every command, option, flag spelling, arity, default, choice list,
repeatability, type and help string, 255 params — and `test_cli_surface.py`
asserts the Click tree still matches it. One thing genuinely could not be
carried across: `click.argument` has no `help=`, so a positional's description
is folded into its command's epilog instead. And one flag changed shape —
`character default-set --set` was `--set a b c` and is now `--set a --set b`,
because Click has no variadic option.

---

## The modules

**This is where the pipeline's internals are named.** A **`studio-media-*`**
skill describes the CLI surface and nothing below it — `studio <command>`, never
a module, a path or a function. A **`studio-code-*`** skill may name them, since
the code is what it is about; `studio-code-pipeline` links here rather than
restating any of it.

`pipeline/scripts/lint_skills.py` enforces the split. The rule exists because
these module tables used to live inside two media skills, where five of the
names rotted into references to files that no longer existed. A doc that names a
module has to be maintained alongside the code — keeping it here, next to this
paragraph, is what makes that possible.

The package is `studio/pipeline/src/studio_pipeline/`, in five subpackages.

**`adapters/` — the outside world.** Nothing here knows about characters, runs
or projects.

| Module | Purpose |
|---|---|
| `s3.py` | The AWS-login-bridged boto3 client, plus get/put/copy/list helpers. One auth path for the whole package. |
| `replicate.py` | Token, HTTP, download, poll. |
| `ffmpeg.py` | Probe, stitch, frame grab, contact grid. A scene and a movie join their inputs by identical rules because they call the same function. ffmpeg ships in the wheel; no system install. |

**`domain/` — the tree and the records in it.**

| Module | Purpose |
|---|---|
| `paths.py` | **The one module that knows the tree's shape.** Every key is built here, which is what keeps a global prefix applied in exactly one place. Library, not a command. |
| `projects.py` | Project CRUD and the project **input pool**. `require_project()` turns a missing `--project` into an error that lists the real options. |
| `runs.py` | The shared **run store** every engine records into: request/prompt/result, output archiving, runref resolution for chaining, `find --character` across projects. It refuses a URL-shaped binding — this is where "S3 is the only origin" is enforced in code. |
| `scenes.py` | The **scene store**: a piece planned, shot and cut, under `projects/<p>/scenes/<slug>/`. Owns the manifest, `assemble`, `handoff`, and the read-only half of the CLI. |
| `storyboard.py` | **The plan document**, pure data: what a shot's panels mean, which one is the start frame once the chain has spoken, how a revision merges onto work already paid for. No S3, no models — so the rules that decide what a shot sends are testable on their own. |
| `movies.py` | The **movie store**: scenes cut into one piece. The same shape one tier up. |
| `frames.py` | Stills out of a run's video — the handoff frame, and the contact grid that lets a clip be looked at before more money is spent on it. Its `chain` store is for a sequence with no scene behind it; a planned scene derives its own frames from `scene.json`. |
| `characters.py` | The character record: bible CRUD, the described reference index, pool listing, the compressed identity block. |
| `curate.py` | The pool operations that go wrong by hand — dedupe, renumber, regroup, move. Every one is a dry run without `--apply`. |
| `rewrite.py` | **When an object moves, the records that name it must follow.** `apply_moves()` is what curation and the migrator call; `check` walks every record and confirms what it names still exists. |
| `prompt.py` | Prompt assembly and validation — the structured object in, the serialized prompt plus engine params out. |
| `phrasebook.py` | Per-model wording lists, kept as data in S3 like characters. |
| `contact_sheet.py` | Labeled thumbnail grids over arbitrary keys. |

**`engine/` — invoking a model.**

| Module | Purpose |
|---|---|
| `models.json` | **The registry.** Data, not code: single source of truth for every model. |
| `registry.py` | Load / look up / list; snapshot saving for refreshes. |
| `runner.py` | `studio run` — builds the payload and invokes *any* registered model. |
| `submit.py` | The one submit lifecycle, image and video alike. |
| `schema.py` | Live schema fetch; validates fields, enums, ranges, `denied`. |
| `refs.py` | Character reference selection and project input pool → S3 keys. |
| `shoot.py` | `studio character shoot` — the STANDARD reference set, one run per slot in `domain/templates/reference_shots.yaml`. Reads the character's bible for the prompt, binds a pose plate from `config/`, then files, describes and indexes each result. Lives here rather than in `domain/` because it invokes models; it drives the same lifecycle as `runner.py` rather than repeating it. |
| `board.py` | `studio scenes board` / `render` / `check` — the two commands that spend money in a scene's life, plus the free one that says whether they would work. Turns the plan's roles into bindings and hands them to the same lifecycle `runner.py` drives. Every cap, exclusion and format rule stays in `submit.py`; a copy here is the one that drifts. |
| `add_model.py` | Onboarding: fetch schema + README, infer an entry, append it to the registry. It writes no documentation — see `studio-media-add-model`. |

**`objects/` — moving bytes.** `upload.py`, `download.py`, `presign.py`
(how assets reach Replicate) and `convert.py` (re-encode so a target engine
accepts it).

**`maintenance/` — one-offs.** `backfill_replicate.py` imports historical
predictions into the run store; `migrate_layout.py` is the move off the
pre-restructure tree, kept for any bucket that still holds one.

---

## How to add a new skill

1. Write the code as a module under `studio/pipeline/src/studio_pipeline/`, in
   the subpackage it belongs to — see [The modules](#the-modules) for what each
   one holds. Expose it as a `click` command or group, so it can also be called
   in-process by another module.
2. Attach it in `cli.py` and put its name in a `_Grouped.SECTIONS` list — a
   command in neither never appears in `studio --help`.
3. Create `studio/.claude/skills/<name>/SKILL.md` with YAML frontmatter — prose
   only. Choose the family: **`studio-media-<name>`** if the skill is for using
   the pipeline, **`studio-code-<name>`** if it is for changing it. A media skill
   invokes `studio <command>` and never names a module, a path or a function; a
   code skill may name them, and they have to exist. No code lives in a skill
   directory either way. `pipeline/scripts/lint_skills.py` fails the build
   otherwise — run it directly, or let pre-commit and the PR workflow run it.
4. If it needs a new dependency, add it to `pipeline/pyproject.toml` and re-run
   `uv sync`. There is one dependency set for the whole pipeline.
5. If it needs new Bash patterns, add them to the **monorepo root**
   `.claude/settings.json`. Claude Code does not read a nested `settings.json`,
   so studio's permissions live at the root even though its skills do not.
6. Add a test. `pipeline/tests/` is moto-backed and needs no AWS; the suite is
   deliberately weighted towards wiring rather than features, because a
   restructure is what actually breaks this code.
7. Document it in the table above, and in `studio/CLAUDE.md`.

To add a new *model* rather than a new skill, use `studio-media-add-model` — models
are data in the registry, not code. That skill also writes the new model's page;
`studio add-model` deliberately generates no documentation.
