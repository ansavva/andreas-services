# studio — the generation pipeline

The local half of studio: the Claude Code skills that produce the media, and
the rules that govern them. For the deployed browser over the output, see
[WEB_APP.md](WEB_APP.md); for the map of both, [../CLAUDE.md](../CLAUDE.md).

Nothing here deploys. These skills run inside Claude on your own machine, under
your own AWS login, and reach the same bucket the app reads. Skills live in
`studio/.claude/skills/`. Scripts use `uv` with PEP 723 inline metadata — each
script declares its own dependencies, no shared venv.

---

## Hard rules

These are not preferences. They hold everywhere in this repo, in every skill,
and in anything written back to it.

### 1. NEVER name a character anywhere in the repo

**No character name appears in this repository — ever.** Not in code, docstrings,
`SKILL.md` files, examples, comments, tests, fixtures, commit messages, branch
names, or pull request titles and bodies.

Characters are **data, not code**: they live only in S3 under `characters/<name>/`
(see `studio-character`). The repo describes the *machinery* that operates on any
character, so it never needs to know one by name.

Use the placeholder `<name>` in every example and help string:

```bash
uv run $STUDIO run --model nano-banana-pro --project <project> \
  --prompt "..." --character <name>
uv run $RUNS outputs <project>/latest --presign
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
the **registry** (`studio-core/scripts/models.json`), and the runner fetches the
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
studio/
├── pipeline/                      — THE CODE (local only, never deploys)
│   ├── pyproject.toml             one dependency set, one console script
│   ├── uv.lock                    committed: this is an app, not a library
│   └── studio_pipeline/
│       ├── cli.py                 `studio` — dispatch over everything below
│       ├── __init__.py            STUDIO_DIR, ENV_FILE, env_value()
│       ├── _invoke.py             in-process calls between the parts
│       ├── store/                 the S3 asset store
│       │   ├── s3.py              credentials bridge, BUCKET/PREFIX/REGION
│       │   ├── paths.py           the one module that knows the tree's shape
│       │   ├── runs.py            the run store; refuses a URL-shaped binding
│       │   ├── scenes.py movies.py frames.py projects.py
│       │   ├── upload.py download.py presign.py convert.py
│       │   └── rewrite.py phrasebook.py video.py
│       ├── engine/                the model layer
│       │   ├── models.json        the REGISTRY — models are data, not code
│       │   ├── runner.py          `studio run` / `studio models`
│       │   ├── submit.py registry.py model_schema.py replicate_api.py refs.py
│       │   └── add_model.py
│       ├── characters/            character.py curate.py contact_sheet.py
│       └── prompt/build.py        structured prompt authoring
│
├── .claude/skills/                — THE DOCS (one SKILL.md each, no code)
│   ├── studio-s3/  studio-core/  studio-character/  studio-prompt/
│   ├── studio-image/  studio-shot/  studio-scene/  studio-movie/
│   ├── studio-seedance/  studio-kling/  studio-add-model/
│   └── studio-nano-banana-pro/ …-2/  studio-gpt-image-2/ …-1-5/
│
├── backend/  frontend/            — THE APP (see WEB_APP.md)
├── infra/                         — Terraform, incl. modules/media (the bucket)
├── scripts/dev-setup.sh           — installs the pipeline, puts `studio` on PATH
├── .env                           — REPLICATE_API_TOKEN (git-ignored)
├── input/  local/  output/        — local working dirs (git-ignored)
└── CLAUDE.md                      — the index over both halves
```

**One constant knows where `studio/` is**: `studio_pipeline.STUDIO_DIR`. Every
module that needs the repo root — `.env`, `local/characters/` — derives it from
there. It used to be recomputed per file as a count of `".."` segments, which
was correct only for that file's depth and silently wrong the moment one moved.

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
`xharness-prod-media-us-east-1`), never in git — see
[`../infra/README.md`](../infra/README.md).

### The two trees — characters and projects

A **character** is an identity record. A **project** is a piece of work. They
used to be one folder, which left work involving two characters with nowhere to
live and work involving none borrowing a fake character called `misc`.

```
characters/<name>/
    profile.yaml    the bible — identity, plus the DESCRIBED reference index
    reference/      generated character imagery, in purpose subfolders
        face/  body/  wardrobe/  scene/ …
    corpus/         collected material about the character — uploads, keeper clips
    seed/           the founding real-world source photos
    archive/        retired material — NEVER used unless the user names it

projects/<project>/
    project.json    name, description, the characters involved
    runs/           one directory per submission
    chains/         a scene's own frames, in order
    scenes/         runs cut into one continuous take
    movies/         scenes cut into one piece
    favorites/      keepers, copied out of runs
    input/          the project working pool (<project>_in_<n>.<ext>)

phrasebook/wording.yaml
```

There is **no `media/` prefix** — the tree is at the bucket root. (There was one,
inherited from mirroring Google Drive 1:1; it bought nothing.)

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
(Separately, the `studio-shot` skill produces a whole still-then-clip chain,
usually one shot in this sense.)

Every submission to Replicate, from any `studio-*` engine, is recorded as a
**run**:

```
projects/<project>/runs/<YYYY-MM-DD_HH-MM-SS>_<slug>/
    request.json    what we sent — references as S3 KEYS, plus `characters[]`
    prompt.json     the studio-prompt source, when one was used
    result.json     prediction id, status, media types, output keys
    output/         the artifact(s) — .mp4, .jpg, however many
```

A run belongs to a project and **names the characters it used**, inferred from
its bindings rather than trusted from the flags. That list is what makes "every
run using this character" answerable now that the folder no longer says it:
`runs.py find --character <name>`.

Scenes and movies take the same id shape, so they sort the same way:

```
projects/<project>/scenes/<YYYY-MM-DD_HH-MM-SS>_<slug>/
    scene.json      the manifest — shots in cut order, as RUNREFS and S3 KEYS
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
| `studio-scene`     | **A piece longer than one generation.** Chains video runs — each starting from the previous clip's last frame — then stitches them into one cut. Owns the chain loop, the continuity rules that keep shots cutting together, the per-shot verification gate, and the `multi_prompt`-cuts-vs-timing trade. Use when a shot outruns the model's duration ceiling or must read as one continuous take |
| `studio-movie`     | **The tier above a scene.** Cuts a project's finished scenes into one piece. Owns the cut order and the movie-vs-longer-scene decision: cut a movie where a hard cut belongs (a change of place, time or subject); extend a scene where it must read as one take |
| `studio-shot`      | **Orchestrates a whole shot**: reads a brief, shows the multi-step plan as JSON for approval, then renders a still and animates it — frame-first, one approval gate per billing step. Use when a brief describes motion or spans more than one studio-* call |
| `studio-core`      | **The shared machinery.** The model **registry** (`models.json`), the one submit lifecycle, live-schema validation, and `studio.py` — the runner that invokes *any* registered model. Models are DATA, not code |
| `studio-add-model` | **Onboard a new Replicate model**: reads its live schema *and* its README, proposes a registry entry for review, then writes it and scaffolds the model's skill. The only way a model should be added |
| `studio-image`     | The **frame-first workflow** for stills — why to render a frame before a video, run chaining, the approval gate, choosing between the image models. Model-agnostic; each model has its own skill |
| `studio-nano-banana-pro` | `google/nano-banana-pro` — strongest all-round image model, the usual default for character frames. Legible text, 4K, ≤14 refs, tunable safety filter. **Never set `allow_fallback_model`** — it reroutes to a different model than the one approved |
| `studio-nano-banana-2` | `google/nano-banana-2` — fast/cheap sibling. The only model with the extreme `1:4`…`8:1` ratios; Google Search / Image Search grounding |
| `studio-gpt-image-2` | `openai/gpt-image-2` — OpenAI's newest. Dense legible text, pixel-exact sizes, references held at high fidelity **automatically**. No transparent background |
| `studio-gpt-image-1-5` | `openai/gpt-image-1.5` — the one that does **transparent backgrounds** and exposes `input_fidelity` (dial face preservation up *or down*). Aspect limited to `1:1`/`3:2`/`2:3` |
| `studio-seedance`  | `bytedance/seedance-2.0` — native audio, first/last frame, reference images/videos/audio. A start frame and a reference set **cannot** be combined |
| `studio-kling`     | `kwaivgi/kling-v3-omni-video` — Kling 3.0 / O3 Omni (~$0.168/s, `reference_images` for consistency, native multi-shot to 6 cuts). Start frame and reference images can be combined |
| `studio-prompt`    | Author prompts as structured JSON for either engine (`--engine seedance\|kling-replicate`); validates rules and routes technical fields + the negative prompt where each engine takes them |
| `studio-character` | Manage on-model characters (create/update/list/curate/load) whose bible + described reference library live in S3 (`characters/<name>/`); characters are data, not skills |
| `studio-s3`               | Read/write the `xharness-prod-media-us-east-1` S3 bucket (list, upload, download, presign) — the asset store holding **characters** and **projects**, plus the shared **run store** (`runs.py`), **scene store** (`scenes.py`) and **movie store** (`movies.py`), the project registry (`projects.py`), the layout module (`paths.py`) and the record rewriter (`rewrite.py`). Storage only; model invocation lives in `studio-core` |

---
## How the code is invoked

Everything is a subcommand of one console script:

```bash
studio --help              # the whole surface, grouped
studio runs --help         # a command's own options
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

---

## How to add a new skill

1. Write the code as a module under `studio/pipeline/studio_pipeline/`, in the
   subpackage it belongs to (`store`, `engine`, `characters`, `prompt`). Give it
   a `main()` that parses `sys.argv` — that is the contract `cli.py` dispatches
   against, and what lets a command be called in-process by another.
2. Add a row to `COMMANDS` and a name to `GROUPS` in `cli.py`.
3. Create `studio/.claude/skills/<name>/SKILL.md` with YAML frontmatter — prose
   only, invoking `studio <command>`. No code lives in a skill directory.
4. If it needs a new dependency, add it to `pipeline/pyproject.toml` and re-run
   `uv sync`. There is one dependency set for the whole pipeline.
5. If it needs new Bash patterns, add them to the **monorepo root**
   `.claude/settings.json`. Claude Code does not read a nested `settings.json`,
   so studio's permissions live at the root even though its skills do not.
6. Document it in the table above, and in `studio/CLAUDE.md`.

To add a new *model* rather than a new skill, use `studio-add-model` — models
are data in `studio-core/scripts/models.json`, not code.
