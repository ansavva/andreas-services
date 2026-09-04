# studio — the generation pipeline

The local half of studio: the Claude Code skills that produce the media, and
the rules that govern them. For the deployed browser over the output, see
[WEB_APP.md](WEB_APP.md); for the map of both, [../CLAUDE.md](../CLAUDE.md).

Nothing here deploys. These skills run inside Claude on your own machine and
reach the library **through the studio API**: `studio login` is the one
credential an ordinary session needs, and nothing here needs an AWS account.
Local work runs against this machine's dev stack, not the bucket the deployed
app reads — see [../CLAUDE.md](../CLAUDE.md). Skills live in
`studio/.claude/skills/`, in two families: **`studio-media-*`** for using the
pipeline to make media, **`studio-code-*`** for working on the pipeline's own
code. The code is one package with one dependency set — see [Layout](#layout).

---

## Hard rules

These are not preferences. They hold everywhere in this repo, in every skill,
and in anything written back to it.

### 1. NEVER name a PRODUCTION character in the repo

**No production character's name appears in this repository — ever.** Not in
code, docstrings, `SKILL.md` files, examples, comments, tests, fixtures, commit
messages, branch names, or pull request titles and bodies.

Characters are **data, not code**: a row in the catalog and a folder of nodes
(see `studio-media-character`). The repo describes the *machinery* that operates
on any character, so it never needs to know one by name.

Use the placeholder `<name>` in every example and help string:

```bash
studio run --model nano-banana-pro --project <project> \
  --prompt "..." --character <name>
studio runs outputs <project>/latest --presign
```

The same goes for **project** names: use `<project>` in examples. And for
anything that identifies a production character indirectly — a scene, a
catchphrase. When writing a commit message or PR about character work, describe
the change to the tooling, not the character it was done for.

#### The exception: a DEV SUBJECT may be named

A **dev subject** is a character that exists only in a per-machine
`studio-dev-<short12>-*` stack and in the shared seed fixture. It never appears
in production. Naming one in the repo is fine, and the fixture requires it: a
fixture carries `catalog.json` into git, and every path in that document is a
name.

Two things make this safe, and they are different in kind:

- **Mechanical.** `dev_seed.source()` refuses to read a bucket or table whose
  name contains `prod` before it reads anything at all, so a fixture is
  dev-origin by construction. There is no path by which a production name
  reaches `catalog.json`.
- **Deliberate.** Which dev subjects may be published is `DEV_SUBJECTS` in
  `scripts/dev_seed/dev_seed/seed.py` — a committed frozenset. Adding one is a
  reviewed diff, and that review is where the question "should this person's
  likeness be in a fixture every machine downloads" gets asked.

A list of names is a better fit for the decision actually being made than any
pattern over a name's shape, which cannot tell a first name from a placeholder.

**Production characters are unchanged.** They are never named, and nothing
about the fixture path reaches them.

### 2. NOTHING runs unless a person tells it to

**Show the user the complete `input` object as JSON — every parameter, not just
the prompt — ask, and submit only when told.** Every submission bills, and a
wrong `duration` or `mode` costs exactly as much as a wrong prompt. Show it
again after *any* edit — a yes covers the payload that was shown, not the next
revision of it. **The submit command is the act, and there is no separate
approve step** (decision 2026-09-04).

**Different models take different inputs.** Seedance takes `image` /
`last_frame_image` / `seed` / `resolution`; Kling takes `start_image` /
`end_image` / `mode` / `multi_prompt` and has no seed at all. Never assume a
field carries over between them. Every model's inputs, caps and caveats live in
the **registry** (`backend/studio_core/models.json`, read over `GET /api/models`),
and the runner fetches the target model's **live input schema** to reject
unknown fields, bad enums and out-of-range numbers — plus documented constraints
the schema does not enforce — before anything bills. Review the payload, then
let the validator confirm the model actually accepts it.

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

`--dry-run` renders exactly this for every model (`domain/runs.py:
render_payload()`); `--dry-run --json` emits the raw payload plus its
`bindings` for machines. Image inputs appear as a presigned-key marker rather
than the signed URL, since the URL itself is ~2 KB of noise and expires.

The rule covers what is sent to the model. The surrounding steps — presigning,
polling, downloads, uploads, recording the run — need no asking.

**`--dry-run` leaves a DRAFT.** The run is created when it is planned rather
than when it is submitted, so the payload printed above has an address: it can
be opened in the app, edited — `studio runs edit`, or the run page's own editor
— read again with `studio runs show`, and sent later with `studio runs submit`
when a person says so. The submit is the act; the API takes a `draft` straight
to the provider and records no approval. See [RUN_PLAN.md](RUN_PLAN.md).

**A yes is to a payload, not to a plan.** A yes to "shall I render this?", an
answer to a multiple-choice question, or a payload shown earlier in the
conversation is not an instruction to send the request about to go out. Show it
again and wait. **There is deliberately no `--yes`-style flag on any generating
command** — `run` submits because it was typed, `scenes board` asks at the
terminal — and a yes-flag there is precisely the door an agent walks through
while believing some earlier exchange counted as being told to. If one appears
on a command that spends, it is a bug. The `--relayed` flag that once recorded
a second-hand yes as a row went with the approve step it belonged to: a recorded
yes was never a stronger claim than a typed command.

### 2b. NEVER put an image into a character without approval

Runs are append-only history and descriptions can be rewritten, but a
character's **references** are who the character is — every later render is
verified against them, and every future generation may be driven by them.
Tagging one `default`, or taking the tag off, is a decision that belongs to the
user and is **separate** from having agreed to spend money on a render.

So a successful generation does not become identity by itself. A run leaves
its result where it is and prints the promotion line; a person looks, and then:

```bash
studio runs outputs <project>/latest --presign            # look first
studio upload --folder <name>/reference <file> && studio describe <node> --tag default
```

The promotion copies inside the bucket, so the run keeps its own output and no
record ends up naming a key that moved.

### 3. S3 is the only origin

**Assets are NEVER uploaded to Replicate.** Everything sent to a model must
already be an S3 object, reaching Replicate only as a short-lived presigned URL
minted at submit time — and signed URLs are never stored. Full detail under
[THE RULE — S3 is the only origin](#the-rule--s3-is-the-only-origin) below;
enforced in code by `domain/runs.py` and by the API.

---

## Layout

The pipeline is **one package** with **one command**. The `SKILL.md` files are
its agent-facing documentation and hold no code.

```
studio/pipeline/
├── pyproject.toml  uv.lock        one dependency set, one console script
├── scripts/                       lint_skills.py, split_angle_sheet.py
├── tests/                         unit/ contracts/ integration/ support/
└── src/                           ← src layout, deliberately (see below)
    └── studio_pipeline/
        ├── cli.py                 `studio` — the root group, wiring only
        ├── errors.py              domain failure -> `error: …` and exit 1
        │                          `reports` for a module that raises, `die` for
        │                          one that finds the problem mid-function.
        ├── profiles.py            NAMED ENVIRONMENTS — which stack answers.
        │                          One resolver behind all five targeting
        │                          values; `--profile` selects, `dev` by default.
        ├── __init__.py            STUDIO_DIR, DEV_ENV_FILE, ENV_FILE, env_value
        │
        ├── adapters/              THE OUTSIDE WORLD — everything with a side effect
        │   ├── store.py           the media store, by path, through the API
        │   ├── entities.py        the entity routes — the ONLY place a route
        │   │                      spelling lives, and the wire surface a test
        │   │                      reads back out of it
        │   ├── api.py             one transport: token, refresh, library header
        │   └── auth.py            Cognito sign-in + the token cache
        │
        ├── session/               who you are, and where you are pointing
        │   ├── commands.py        `studio login` / `logout` / `whoami`
        │   └── profile_commands.py  `studio profile` list / show / use / sync
        │
        ├── domain/                WHAT THINGS ARE — records and the tree's shape
        │   ├── paths.py           the starting layout names, `join`, `by_name`
        │   ├── runs.py  scenes.py  storyboard.py  movies.py  frames.py
        │   ├── renders.py         ask the service to encode; wait; fetch
        │   ├── projects.py
        │   ├── characters/       base.py profile.py refs.py pools.py cli.py
        │   ├── curate.py  contact_sheet.py
        │   ├── phrasebook.py  prompt.py
        │   ├── templates.py       move the template library between stacks
        │   └── templates/profile.yaml
        │
        ├── engine/                MODEL INVOCATION
        │   ├── resubmit.py        send a draft — `studio runs submit`
        │   ├── runner.py          `studio run`
        │   ├── board.py           `studio scenes board` / `render` / `check`
        │   ├── registry.py  registry_file.py  schema.py  submit.py  refs.py  add_model.py
        │   │                     submit.py is the AUTHORING half; the half
        │   │                     that bills is the API's
        │
        └── objects/               raw object access
            └── upload.py  download.py  presign.py  describe.py
                convert.py  crop.py  config_sync.py
```

Dependencies point one way: `cli` → `domain` → `adapters`. The package's
dependencies are `click`, `pyyaml`, `pycognito` and `boto3`, the last for one
caller — `profiles.aws_session()`, which `profile sync` uses to find the API.
Nothing under `adapters/` opens an S3 or DynamoDB client, and there is no
provider client, no `ffmpeg` and no Pillow in this wheel.

**Why `src/`.** Without it, Python puts the working directory first on the
import path, so tests can pass against files that were never packaged.
`templates/profile.yaml` is package data reached at runtime; a wheel missing it
fails only when someone runs the command. `src/` forces the tests to exercise
the installed package.

**One constant knows where `studio/` is**: `studio_pipeline.STUDIO_DIR`. It
searches upward for the directory holding both `backend/` and `pipeline/`
rather than counting `".."` segments — a count is right only for one file's
depth.

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

Then pick an environment and sign in to it — **the token is the one credential
an ordinary session needs**:

```bash
studio profile list      # what exists; dev is the default and prod is the other
studio login             # signs in to the profile in force
studio whoami            # who, where, and which libraries that reaches
```

`dev-setup.sh` has already run `studio profile sync dev`, so the dev profile
names this machine's stack. `studio profile sync prod` writes the other one from
`/studio/prod/*` in SSM, and then `studio --profile prod <command>` reaches the
deployed library. That is a real target with real money behind it — read
[../CLAUDE.md](../CLAUDE.md#reaching-production---profile-prod) first.

`adapters/auth.py` signs in to Cognito, `adapters/api.py` carries the token on
every call, and `adapters/store.py` addresses the library by path. No bucket
name and no AWS credentials anywhere in that path.

External tools:
- **An AWS account** — **needed by `studio profile sync` and by nothing else.**
  `sync` reads a dev stack's Terraform outputs and prod's SSM parameters, which
  is how the CLI learns the API URL every other command then talks to; it cannot
  go through the API because it is what finds the API. That one call site is
  `profiles.aws_session()`, and boto3's own chain resolves the credentials.
- **ffmpeg** — `brew install ffmpeg` — optional, for checking a render by hand.
  Every encode the pipeline needs is a render job the API runs.

API keys:
- **REPLICATE_API_TOKEN** — https://replicate.com/account/api-tokens — **not
  read by the CLI.** `studio run` asks the API to submit; `studio models show`,
  `studio models refresh` and `studio add-model` read a live schema through
  `GET /api/models/<name>/schema`. What needs the token is whichever API you
  are pointed at:

  | Where | How |
  |---|---|
  | The deployed API | An SSM SecureString, `/studio/prod/replicate-api-token`, read by the Lambda under its own role. The value comes from the `REPLICATE_API_TOKEN` **environment secret** on `studio-production`, written there by `studio-prod.yaml` on every app deploy. Terraform creates the parameter and never holds the value. |
  | A local API under `dev-up.sh` | `~/.config/andreas-services/studio/dev.env`, the file that already holds this machine's dev pool password. `dev-up.sh` sources it into the Flask process. |

  ```
  REPLICATE_API_TOKEN=r8_…
  ```

  There is deliberately **no per-machine SSM parameter**: a token is not
  environment-scoped, so a developer's own file is the right place for it and a
  parameter per machine would be a secret per machine to rotate. For the same
  reason it is **not a profile field**.

  A line left in `studio/.env` is inert — nothing in the pipeline reads it.
  `dev-setup.sh` still warns about it, because a secret inside the repo is worth
  removing whether or not anything loads it: `.gitignore` protects a secret
  from `git add` and from nothing else — not from `git add -f`, not from a copy
  of the working tree, not from a backup tool that indexes the repo.

Asset storage needs **neither an AWS login nor a key of its own.** Character
profiles, reference images and every generated asset live in S3 and never in
git, but the CLI reaches them through the API on the token `studio login` stored
and never names a bucket. Which bucket answers depends on where you are: locally
it is this machine's dev stack's, and `studio-prod-media-us-east-1` is the
deployed app's. See [`../infra/README.md`](../infra/README.md).

### The two trees — characters and projects

A **character** is an identity record. A **project** is a piece of work. Work
involving two characters, or none, has a project of its own rather than
borrowing a character's folder.

**A character and a project are ROWS, and each owns a folder.** The folder is
where their material lives; the record is what they are. Both folders sit
directly under the library root — there is no `characters/` or `projects/`
wrapper, because an entity is found by querying the table, not by listing a
folder.

```
<character>/        a folder node the character's `root` names
    reference/      where identity images conventionally sit — a convention,
                    not a rule: the `default` tag is what makes one identity
        face/  body/  wardrobe/  frame/ …
    corpus/         collected material — uploads, keeper clips
    seed/           the founding real-world source photos
    archive/        retired material — NEVER used unless the user names it

<project>/          a folder node the project's `root` names
    runs/           one folder per submission
    chains/         an ad-hoc sequence's frames (a planned scene derives its own)
    scenes/         runs cut into one continuous take
    movies/         scenes cut into one piece
    input/          the project working pool

config/             the angle images, shared by the library and owned by no entity
    angle/body/*.png    how to stand, cited by a template's illustration
    angle/face/*.png     head-angle images
```

**There is no `profile.yaml` and no `project.json`.** The bible is a validated
map on the character's row and the project's description is a field on its own.
**The phrasebook is `TERM#` rows**, not a document in this tree.

**The five folder names under a project and the four under a character are
convention, not schema.** The API creates them with the entity and resolves them
by name when it needs one, making it if it is absent. Rename `runs/` and the next
run makes a new one; every existing run is still reachable, because a run record
names its own folder node. A folder someone makes by hand is as real as the ones
that came with the entity.

**None of these names appears in an S3 key.** A key is
`<characters|projects|libraries>/<entity id>/<node id>.<ext>`, stamped once when
the node is created and never parsed. The tree above is the catalog's; the
bucket holds bytes under ids.

**`config/` is the one tree whose source of truth is the repo.** It lives at
`studio/config/`, and `studio config sync` pushes it into the library as
ordinary nodes — `scripts/dev-shared-material.sh` wraps that, and
`dev-setup.sh` calls it. The library holds a copy because a model may only be
handed a presigned URL of an S3 object; an angle image that was never synced
cannot be used, and a shoot checks for them before spending anything. Editing
an angle image in the library rather than the repo is how they diverge.

**Ask which project before generating anything.** `--project` is required and
never inferred: where output lands is the one thing rerunning a command cannot
undo. Offer the existing projects (`studio projects list`) and the option of a
new one (`studio projects new`), and settle it *before* showing a payload — a
yes to a payload must never imply a yes to where it lands.

### The tiers — run, shot, scene, movie

```
generation cut  ⊂  shot  ⊂  scene  ⊂  movie
```

A **generation cut** is a cut inside one submission (Kling `multi_prompt`). A
**shot** is one run's output used as a scene component. A **scene** is shots
stitched into one continuous take. A **movie** is scenes cut together.
(Separately, the `studio-media-shot` skill produces a whole still-then-clip chain,
usually one shot in this sense.)

Every submission to Replicate, from any `studio-*` engine, is recorded as a
**run**:

**A run is a row with a folder.** The envelope — status, model, prediction id,
timings, cost, bindings, outputs — is `RUN#<id>`/`META`, and it is studio's to
validate and query. The provider's own documents stay bytes:

```
<project>/runs/<run id>/                          the folder the record names
    request.json    what we sent, verbatim        ─┐  payload blobs.
    prompt.json     the prompt source, when used   ├─ studio stores these
    result.json     what came back, verbatim      ─┘  and decodes none of them
    output/         the artifact(s) — .mp4, .jpg, however many
```

That split is the point. The pipeline changes the payload's shape freely, so
nothing may parse it; but "which runs used this character, on which model, and
what did they cost" is a question about studio's own bookkeeping, and it has an
answer. **`bindings` are node ids**, so a run that consumed an image still
resolves it after that image is renamed or moved.

A run belongs to a project and **names the characters it used**, inferred from
its bindings rather than trusted from the flags, which is what makes
`studio runs find --character <name>` one query rather than a walk over every
project's every run folder.

The folder name starts with a timestamp, which is convenient when browsing and
is not an id: the run's id is a UUID and nothing derives one from the other.

A **scene is a row with a UUID** and created before anything renders — it is
the plan as much as the record. A **movie** is only ever a finished cut:

```
<project>/scenes/<scene_id>/
    storyboard/     the panels: shot-<NN>-p<M>.png
    shots/          each source clip, copied in, numbered in cut order
    output/         the stitched scene — <name>.mp4

<project>/movies/<movie_id>/
    scenes/         each scene's output, copied in, numbered in cut order
    output/         the finished movie — <name>.mp4
```

A scene is `SCENE#<id>`/`META` with one `SHOT#` row per planned shot, and a
movie is its own record naming scenes in cut order. A shot's `order` is an
attribute, so revising a plan moves rows rather than rewriting a document.

Both are **derived, never a source of truth**: the runs they name remain the
history, so either can always be rebuilt. Sources are copied in so a scene stays
playable as its runs accumulate around it, and the record names the originating
ref beside the copied node — copying does not lose lineage. Both stitch through
the same function, **in the service**: `backend/studio_core/media/ffmpeg.py`'s
`stitch()`, which stream-copies when the inputs already agree on codec,
geometry, frame rate and audio layout, and re-encodes (recording that it did)
when they don't.

**Every encode is a render job.** A second container image
(`backend/Dockerfile.render`) carries `ffmpeg`; `POST /api/renders` enqueues
onto `studio-prod-render`, and a worker Lambda does the download, the stitch
and the record. `domain/renders.py` is this side of that seam: it resolves
inputs to node ids, posts one job and polls the row. `convert` and `crop` are
**not** on that queue — both are sub-second on one image, so they are
synchronous routes in the API image with Pillow and no ffmpeg.

### Identity vs working material — never conflate them

A character's **reference set** is a library of generated character imagery,
found by tag, and described one file at a time. The engines cap what they
accept and send it in full, so a *subset* is chosen deliberately — `--pick`,
`--pick-tag`, or the character's `default` images. An over-cap selection is
**refused**, with the index printed, rather than truncated: which images a
generation saw should not be decided by whatever a folder listing returned. The
API resolves the selection (`GET /api/characters/<id>/selection`), so the CLI
and the app cannot disagree about what a model was shown.

A project's `input/` pool is the **working pool** — uploads and frames pulled
off clips to drive the next generation. Uncapped, picked from by number
(`--input N`), never identity.

**A frame pulled off a run goes to the project pool.** Promoting one into a
character's `reference/` feeds model output back in as identity and compounds
drift; it is a deliberate curation decision, and it should be described when it
happens.

**Records name node ids, so a move invalidates nothing.** A rename or a move
changes a node's name or parent; every run, scene, movie and chain pointing at
that node stays correct, and there is nothing to carry along.

The **run owns its output**; medium is an attribute, never a folder name, so one
video and ten images take the same shape. `runs/` is **append-only history**.
Runs chain: one run's output feeds the next as a start frame (`--start-run`) or
as reference material (`--ref-run`), addressed by **runref**
(`<project>/latest#1`).

### THE RULE — S3 is the only origin

**Assets are NEVER uploaded to Replicate.** Anything sent to a model must already
be an S3 object, and reaches Replicate only as a short-lived **presigned URL**
minted at submit time. Signed URLs are never *stored* either — run records hold
node ids, because URLs expire, are ~2 KB of noise each, and carry time-limited
bucket access that must not outlive the request. `domain/runs.py` refuses a
URL-shaped binding and so does `POST /api/runs`, so this is enforced in code.
To use a local file, upload it to S3 first.

---

## Available skills

All live in `studio/.claude/skills/` and are discovered as `studio:<name>` —
directory-scoped, so they surface when the work is under `studio/`. Eighteen
are `studio-media-*` and one is `studio-code-*`; `ls` that directory rather
than trusting this number.

| Skill     | What it does                                              |
|-----------|-----------------------------------------------------------|
| `studio-media-scene`     | **A piece longer than one generation.** Chains video runs — each starting from the previous clip's last frame — then stitches them into one cut. Owns the chain loop, the continuity rules that keep shots cutting together, the per-shot verification gate, and the `multi_prompt`-cuts-vs-timing trade. Use when a shot outruns the model's duration ceiling or must read as one continuous take |
| `studio-media-movie`     | **The tier above a scene.** Cuts a project's finished scenes into one piece. Owns the cut order and the movie-vs-longer-scene decision: cut a movie where a hard cut belongs (a change of place, time or subject); extend a scene where it must read as one take |
| `studio-media-shot`      | **Orchestrates a whole shot**: reads a brief, shows the multi-step plan as JSON to read, then renders a still and animates it — frame-first, show-then-ask at every billing step. Use when a brief describes motion or spans more than one studio-* call |
| `studio-media-core`      | **The shared machinery.** The model **registry** (the backend's `models.json`, served at `GET /api/models`), the one submit lifecycle, live-schema validation, and `studio run` — the runner that invokes *any* registered model. Models are DATA, not code |
| `studio-media-add-model` | **Onboard a new Replicate model**: reads its live schema *and* its README, proposes a registry entry for review, then writes it to the registry. Also owns writing the new model's skill page — nothing generates it. The only way a model should be added |
| `studio-media-image`     | The **frame-first workflow** for stills — why to render a frame before a video, run chaining, the show-then-ask rule, choosing between the image models. Model-agnostic; each model has its own skill |
| `studio-media-image-upscale` | `topazlabs/image-upscale` — enlarge and restore an image that already exists. The only registered model that restores rather than generates |
| `studio-media-nano-banana-pro` | `google/nano-banana-pro` — strongest all-round image model. Legible text, 4K, ≤14 refs, tunable safety filter. **Never set `allow_fallback_model`** — it reroutes to a different model than the one shown |
| `studio-media-nano-banana-2` | `google/nano-banana-2` — fast/cheap sibling. The only model with the extreme `1:4`…`8:1` ratios; Google Search / Image Search grounding |
| `studio-media-gpt-image-2` | `openai/gpt-image-2` — OpenAI's newest, and **the default for character frames**. Dense legible text, pixel-exact sizes, references held at high fidelity **automatically**. No transparent background |
| `studio-media-gpt-image-1-5` | `openai/gpt-image-1.5` — the one that does **transparent backgrounds** and exposes `input_fidelity` (dial face preservation up *or down*). Aspect limited to `1:1`/`3:2`/`2:3` |
| `studio-media-seedance`  | `bytedance/seedance-2.0` — native audio, first/last frame, reference images/videos/audio. A start frame and a reference set **cannot** be combined |
| `studio-media-kling`     | `kwaivgi/kling-v3-omni-video` — Kling 3.0 / O3 Omni (~$0.168/s, `reference_images` for consistency, native multi-shot to 6 cuts). Start frame and reference images can be combined |
| `studio-media-veo-3-1`   | `google/veo-3.1` — the control-oriented engine, and the only one with a repeatable **seed** and a real `negative_prompt`. Reference images work only at 16:9 and 8 seconds; durations are a 4/6/8s enum |
| `studio-media-grok-imagine-video` | `xai/grok-imagine-video` — animates one chosen still, any integer 1–15s, and is the only registered model that **edits an existing clip**. No reference images, so not for holding a character on-model |
| `studio-media-prompt`    | Author prompts as structured JSON for either engine (`--engine seedance\|kling-replicate`); validates rules and routes technical fields + the negative prompt where each engine takes them |
| `studio-media-character` | Manage on-model characters (create/update/list/curate/load) whose bible is a field on the character's row and whose identity images are files carrying `default`; characters are data, not skills |
| `studio-media-s3`        | Address the media store through the API by name path (list, upload, download, presign) — the asset store holding **characters** and **projects**, plus the run, scene and movie stores. Storage only; model invocation lives in `studio-media-core` |
| `studio-code-pipeline` | **The other family, and the only member of it.** Changing the pipeline's own code — a subcommand, a module move, the registry's machinery, a wiring failure, a test. Not for making media |

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

| | |
|---|---|
| `studio run` | submit a generation (creates a run) |
| `studio runs` | the run store — `list`, `show`, `find`, `submit`, `edit`, `delete` (reads and edits runs) |

The parsing is **Click**. `pipeline/tests/contracts/cli_surface_reference.json`
records every command, option, flag spelling, arity, default, choice list,
repeatability, type and help string, and
`pipeline/tests/contracts/test_cli_surface.py` asserts the Click tree still
matches it. Regenerate it with `tests.contracts.update_cli_reference` when the
surface changes deliberately — never edit it to make a test pass.
`click.argument` has no `help=`, so a positional's description is folded into
its command's epilog.

---

## The modules

**This is where the pipeline's internals are named.** A **`studio-media-*`**
skill describes the CLI surface and nothing below it — `studio <command>`, never
a module, a path or a function. A **`studio-code-*`** skill may name them, since
the code is what it is about; `studio-code-pipeline` links here rather than
restating any of it.

`studio/pipeline/scripts/lint_skills.py` enforces the split. A doc that names a
module has to be maintained alongside the code — keeping the tables here, next
to this paragraph, is what makes that possible.

The package is `studio/pipeline/src/studio_pipeline/`, in five subpackages plus
three modules at its root.

### What is local, and why

The pipeline is a thin client over the API. What stays on this side does so for
a reason a route cannot answer:

| Still here | Why it cannot be a route |
|---|---|
| `profiles.py`, `adapters/auth.py` | How the CLI **finds** the API. `profiles.aws_session()` is the one boto3 call in the package, and a call that locates a service cannot go through it. |
| `engine/submit.py`'s authoring half, `engine/board.py`, `engine/runner.py` | **Hard rule #2.** They gather, preflight, render the two documents a person reads, and record a draft. The half that spends is `POST /api/runs/<id>/submit`. A service has nobody in front of it; the half only a person can perform stays where the person is. |
| `engine/refs.py`, `engine/schema.py` | Already thin — a selection is `GET /api/characters/<id>/selection` and a schema is `GET /api/models/<name>/schema`. What is left is the message a refusal needs, which a 409 body cannot carry. |
| `engine/registry_file.py`, `engine/add_model.py`'s inference | They edit a **committed file**. A write route would put a reviewed repo change behind an HTTP call. |
| `domain/storyboard.py`'s role and frame helpers | Read by `board.py` on material it has just built and **not yet written** — the one case a served derivation cannot answer. |
| `domain/renders.py`, and the resolution in front of every render job | `latest`, `#N`, "that scene is not cut yet" are refusals with an action in them. At the far end of a queue they arrive twenty seconds later as a failed row. |
| the local-file halves of `upload`, `download`, `describe`, `presign`, `prompt`, `character edit`, `config sync` | A service cannot see this machine's disk. `--src` on `contact-sheet` is refused for exactly this reason. |

**At the root.** `cli.py` is wiring and nothing else — a command is attached
there and named in a `_Grouped.SECTIONS` list, or it never appears in
`studio --help`. `errors.py` turns a domain failure into `error: …` and exit 1.
**`profiles.py` decides which stack an invocation is talking to** — the five
targeting values, the file they live in, and the order they resolve in. Read its
docstring before changing anything that reads a bucket, a table, an API URL or
a pool id: the resolution order is not symmetric, and both directions are
deliberate.

**`adapters/` — the outside world.** Nothing here knows about characters, runs
or projects.

| Module | Purpose |
|---|---|
| `store.py` | **The media store, addressed by path and reached through the API.** Resolve a name path to a node, list its files in natural order, read, write, upload, presign, and ensure a folder exists. No bucket name, no credentials — bytes travel to S3 directly on presigned URLs the API signs, which is what keeps a video out of the Lambda's request limit. |
| `entities.py` | **The entity routes — the only place in the package that knows one's spelling.** Characters, projects, runs, scenes, movies, templates, the phrasebook, models, the prompt checker, renders and images. `test_the_route_table_is_the_whole_wire_surface` (`pipeline/tests/unit/adapters/test_entities.py`) reads the `/api/…` literals straight out of this file and `store.py` and asserts them against a table in both directions — a wrapper with no caller has to go rather than be left, because it would put a route in that table that nobody reconciles. |
| `api.py` | One transport for every call the CLI makes: bearer token, refresh-on-401, library header, error mapping. Decided once so no caller re-decides it. |
| `auth.py` | The Cognito sign-in behind `studio login`, and the token cache it writes — **keyed by profile**, so a prod session and a dev session coexist. There is no default API URL: unset is a refusal, not a silent connection to production. It builds an unsigned Cognito client — `InitiateAuth` needs no AWS identity, but boto3 resolves the credential chain at construction and would fail first. |

**`session/` — who you are, and where you are pointing.** `commands.py` is
`studio login` / `logout` / `whoami`; everything the CLI knows about identity it
reads back off the stored token. These work on a machine with **no AWS
credentials configured at all**. `profile_commands.py` is `studio profile
list` / `show` / `use` / `sync`. A session belongs to a profile, `login` signs
you in to the one in force, and `whoami` prints it first. `sync` is the only
member that needs AWS — it reads a dev stack's Terraform state or prod's SSM
parameters, so that no id is ever typed into a config file by a person.

**`domain/` — the tree and the records in it.**

| Module | Purpose |
|---|---|
| `paths.py` | **The starting layout names, address joining, and `by_name` — and nothing else.** `by_name` matches a name over a listing CLIENT-SIDE and refuses an ambiguous one with the ids, because the API resolves ids only. An entity record names its own nodes, so nothing builds a path to assert where something must be. |
| `projects.py` | Project CRUD through the entity routes, plus the **input pool**. `require_project()` turns a missing `--project` into an error that lists the real options. Creating a project is one call: the API writes the record, the library index row, the root folder and the starting subfolders in one transaction, so there is no half-made project to recover from. |
| `runs.py` | The shared **run store** every engine records into: the envelope, output uploads, runref resolution for chaining, `find --character` across projects — one API query. `check_bindings` refuses a URL-shaped binding, and so does the API; keeping the check here as well is what makes a `--dry-run` refuse before anything is sent. |
| `scenes.py` | The **scene store**: a piece planned, shot and cut. Owns the shot rows, the read-only half of the CLI, and the resolution `assemble` and `handoff` do before they hand off — both are render jobs, so what is on this side is turning `latest`, `#N` and "that scene is not cut yet" into node ids and a refusal a person can act on. `new_scene` writes a scene that has never existed; the catalog has no folder until something asks for one. |
| `storyboard.py` | **What is left of the plan document on this side.** Normalising an authored plan, validating it, merging a revision onto rendered work and deriving every status are `backend/studio_core/services/storyboard.py`. What stays: reading a plan off local disk, refusing a nameless scene before a request is spent on it, and the role and frame helpers `engine/board.py` needs **on material it has just built and not yet written**. Those follow `board.py` if it ever moves, and not before. |
| `movies.py` | The **movie store**: scenes cut into one piece. The same shape one tier up, including the folders a cut needs. Copying a scene in is a read plus a write, so each copy is its own blob — one blob under two rows is not on offer, because a delete does not ask whether a blob is still referenced. |
| `frames.py` | Stills out of a run's video — the handoff frame, and the contact grid that lets a clip be looked at before more money is spent on it. It resolves a runref to one video **node** and enqueues a render job; the clip is never downloaded here. Its `chain` store is for a sequence with no scene behind it; a planned scene derives its own frames from its shot rows. |
| `renders.py` | **Asking the service to encode something, and waiting for it.** Enqueue, poll the `render-<uuid>` row, fetch the node it produced. `Ctrl-C` abandons a wait rather than the work, exactly as `engine/submit.wait_for` does — the job is being done elsewhere and the row is still there to read. |
| `characters/` | The character record, in four modules. `base` — names, pools, node helpers. `profile` — the bible: schema, and the `edit` local round trip whose conflict check is a `rev` sent with the write, so the API refuses a stale push itself (compare-and-swap, not check-then-write). `refs` — what a model gets shown: `images` lists the branch with its tags, `selection` is resolved by the API. `pools` — corpus/seed/archive, material rather than identity. `cli` assembles the group; commands are `@click.command` and registered there, which is what keeps the package acyclic. A rename is one `PATCH` of one field, because the name is a plain attribute. |
| `curate.py` | The pool operations that go wrong by hand — `dedupe`, `groups`, `move`, `drop`. There is no order to maintain and a group is a tag, so regrouping is `studio describe` and writes no object. `move` is the one worth knowing — when a byte-identical copy is already in the destination it deletes the source instead, which is the one path here that removes an image. `digest` is an MD5 over the node's bytes. |
| `prompt.py` | **Reading the object and printing the answer, and nothing else.** The rules — one camera move per shot, no bare "fast", no camera verbs in the action, the beat budget, the start-frame redundancy warning — are `backend/studio_core/services/prompt.py` and reachable at `POST /api/prompt`, so the SPA can run the same check. |
| `phrasebook.py` | Per-model wording lists, as `TERM#` rows. The first `add` writes the first term; there is no document to seed. |
| `templates.py` | `studio templates pull` / `push` / `show` — move the template library between stacks as one document. |
| `contact_sheet.py` | Labeled thumbnail grids over a character pool. It walks the pool **recursively**, like `characters/refs`: `reference` is the default and holds group folders rather than images, so a one-level listing would report the commonest invocation as an empty pool. Each tile's caption carries its group, because `face/<name>_1` and `body/<name>_1` share a basename. **The layout is a render job**, on the queue rather than a synchronous route, because what is unbounded here is N downloads where N is a character pool. `--src` is refused: a worker cannot see this machine's disk. |

**The duplicate-submission guard is a query.** `submission_fingerprint` derives
one from `plan_digest` — which already hashes the plan and the ordered sends —
plus the model, so there is no second hash to keep in step; the API stamps it
on the draft and `GET /api/runs?fingerprint=` is one query. Both functions live
in `backend/studio_core/services/digest.py`, which is a module for one reason:
so the CLI's tests can load them. It imports `hashlib`, `json` and `decimal`
and nothing else — the same precondition `services/storyboard.py` and
`services/prompt.py` meet for the same fake —
and `test_a_shared_backend_service_stays_loadable_from_here`
(`pipeline/tests/contracts/test_wiring.py`) asserts it statically, so a Flask
import arrives as a named failure. `catalog.py` re-exports both.

The check runs *after* the draft is created, because the draft is what carries
the fingerprint — the CLI reads the value rather than computing it
(`submit.already_submitted`). A draft costs a row and no bytes, so the check is
free, and the never-billed states are excluded so an abandoned draft cannot make
the next identical payload look like a duplicate. It catches a second machine
and a colleague, which a per-machine file never could.

**`engine/` — invoking a model.**

| Module | Purpose |
|---|---|
| `registry.py` | **Reads the registry, over the wire.** `GET /api/models` via `adapters/entities.models`, memoised once per process. The file itself is `backend/studio_core/models.json`, so the API and the SPA measure a reference selection against the same entries the CLI does. |
| `registry.py`'s `defaults` | **What studio sets when a caller does not.** An authored `defaults` block on an entry, applied by `build_payload` **under** everything a caller asked for — so `--extra`, an `--input-file` and an explicit `per_model` block all still win. Not to be confused with `snapshot.<field>.default` sitting beside it, which records what the PROVIDER does and is rewritten wholesale by `models refresh`; a studio decision parked there would be reverted by the next refresh. Per-model, because the fields are not shared: `quality` and `moderation` are the two OpenAI models' and `nano-banana-pro` spells the same idea `safety_filter_level`. |
| `registry_file.py` | **Writes it.** The repo file, for the only two commands that edit it — `add-model` and `models refresh`, both of which are really asking the API to ask Replicate what a model accepts. Separate from the reader on purpose: reading works against any environment, writing is a reviewed repo change that reaches production on deploy. |
| `runner.py` | `studio run` — builds the payload and invokes *any* registered model. |
| `submit.py` | **The AUTHORING half of the submit lifecycle**, image and video alike: gather every image input as node ids, preflight, render the two documents hard rule #2 asks a person to read, and record the draft. The billing half — presign, create the prediction, upload the output, close the run — is `POST /api/runs/<id>/submit` and a callback. `wait_for` watches the run *row*, so `Ctrl-C` abandons a wait rather than a generation. |
| `schema.py` | Validates fields, enums, ranges and `denied` — off a schema fetched through `GET /api/models/<name>/schema`. The API runs its own copy of the check at submit time, because the SPA also submits and never passes through here; that one is the gate and this one is the better message. |
| `refs.py` | Character reference selection and project input pool → **node ids**. Selection itself is `GET /api/characters/<id>/selection`, so the CLI and the SPA cannot disagree about which images a generation saw; what is here is the translation, and the over-cap refusal that names the commands which narrow a set. |
| `resubmit.py` | Send a draft a person has said to send — `studio runs submit`, and the retry path. Separate from `runner.py` because there is nothing to author: the plan and the sends are on the row, so this is a status check and one `POST`. |
| `board.py` | `studio scenes board` / `render` / `check` — the two commands that spend money in a scene's life, plus the free one that says whether they would work. Turns the plan's roles into bindings and hands them to the same lifecycle `runner.py` drives. Every cap, exclusion and format rule stays in `submit.py`; a copy here is the one that drifts. |
| `add_model.py` | Onboarding: fetch schema + README **through the API**, infer an entry, append it to the registry. The inference stays here because what it produces is a repo file somebody reviews. It writes no documentation — see `studio-media-add-model`. |

**`objects/` — moving bytes.** `upload.py`, `download.py`, `presign.py`
(how assets reach Replicate), `describe.py` (a caption and tags on a node,
which is what makes a reference index selectable), `convert.py` (re-encode so
a target engine accepts it), `crop.py` (cut a rectangle out of one) and
`config_sync.py` (`studio config sync` — push the repo's `config/` angle images
into the library, the one command here whose source is this checkout rather
than the tree).

**`convert` and `crop` are one `POST` each, and Pillow is not in this wheel.**
They are the two operations that deliberately are *not* on the render queue:
both are sub-second on a single image, so an enqueue plus two polls would cost
more wall clock than the work. `backend/studio_core/routes/images.py` argues
the split. What stays here is the part a route should not decide. `--for kling`
is a registry lookup answering "is a conversion needed at all", and an
already-acceptable source makes no request. `--dest-key` ensures the
destination folder first, since the catalog has no folder until something asks
for one; **`upload` ensures its `--folder` for the same reason**. `crop.py`
reuses `convert`'s source resolution and destination handling; what is its own
is the box parser, where every error message names the way the box was wrong —
`LEFT,TOP,WIDTH,HEIGHT` instead of `LEFT,TOP,RIGHT,BOTTOM` being the commonest.
The box is parsed on both sides and that is not duplication worth removing: a
refusal that arrives before a request beats one that arrives as a 400, and the
route has to check anyway because the SPA is not this command. It contains no
subject detection: a wrong box is worse than no command.

A repeated conversion lands `frame (2).jpg` beside the first rather than
overwriting it — `catalog.create_numbered` never clobbers. A `--dest-key` with
no slash in it lands beside the source rather than in the library root.

**Seeding is not in this package.** `scripts/dev_seed/` is its own uv project,
invoked as `dev-seed` and wired into `scripts/dev-aws-seed.sh`. It is the one
job that genuinely needs AWS clients — it writes the rows and copies the blobs a
library is *made of*, before there is a session or often a library. Its
`pyproject.toml` carries that argument.

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
   directory either way. `studio/pipeline/scripts/lint_skills.py` fails the
   build otherwise — run it directly, or let pre-commit and the PR workflow run
   it.
4. If it needs a new dependency, add it to `pipeline/pyproject.toml` and re-run
   `uv sync`. There is one dependency set for the whole pipeline.
5. If it needs new Bash patterns, add them to the **monorepo root**
   `.claude/settings.json`. Claude Code does not read a nested `settings.json`,
   so studio's permissions live at the root even though its skills do not.
6. Add a test. `pipeline/tests/` needs no AWS; the suite is deliberately
   weighted towards wiring rather than features, because a restructure is what
   actually breaks this code. **Do not stub the provider in it** — there is
   nothing on this side to stub. Submitting is `POST /api/runs/<id>/submit`,
   which `pipeline/tests/support/fake_api.py` answers without a socket, and the
   seam a test controls is `fake_api.submits_refused` ("nothing may submit",
   which is stronger than "nothing may bill"). An autouse socket guard sits
   behind that for anything reached indirectly. See `studio-code-pipeline`.
7. Document it in the table above, and in `studio/CLAUDE.md`.

To add a new *model* rather than a new skill, use `studio-media-add-model` — models
are data in the registry, not code. That skill also writes the new model's page;
`studio add-model` deliberately generates no documentation.
