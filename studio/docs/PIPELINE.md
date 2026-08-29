# studio — the generation pipeline

The local half of studio: the Claude Code skills that produce the media, and
the rules that govern them. For the deployed browser over the output, see
[WEB_APP.md](WEB_APP.md); for the map of both, [../CLAUDE.md](../CLAUDE.md).

Nothing here deploys. These skills run inside Claude on your own machine and
reach the library **through the studio API**: `studio login` is the one
credential an ordinary session needs, and nothing here needs an AWS account at
all (#308). Nor is it the bucket the deployed app reads — local work runs
against this machine's dev stack. This sentence read "under your own AWS login,
and reach the same bucket the app reads", and both halves are now wrong: #308
took the login away and #287 the shared bucket. See
[../CLAUDE.md](../CLAUDE.md). Skills live in
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

The same goes for **project** names: a project is usually named after the work,
but today's are named after characters, so use `<project>` in examples too. And
for anything that identifies a production character indirectly — a scene, a
catchphrase, a distinctive slug. When writing a commit message or PR about
character work, describe the change to the tooling, not the character it was
done for.

#### The exception: a DEV SUBJECT may be named

**This rule used to be absolute, and the absolute form is what it says above
minus the word "production".** It was narrowed in August 2026, when the dev seed
fixture was finally published — because the absolute form made the fixture
impossible to complete.

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
  `maintenance/dev_seed.py` — a committed frozenset. Adding one is a reviewed
  diff, and that review is where the question "should this person's likeness be
  in a fixture every machine downloads" gets asked.

What this replaced was a pair of REGEXES: names had to match
`subject-a`/`demo`/`<word>`, and any Title Cased segment was refused outright.
The pattern could not tell `mira` from `demo` — its own docstring said so — so it
refused every capitalised folder and admitted every lowercase first name. A list
of names is a worse fit for a machine and a much better fit for the decision
actually being made.

**Production characters are unchanged.** They are still never named, and nothing
about the fixture path reaches them.

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
the **registry** (`backend/studio_core/models.json`, read over `GET /api/models`), and the runner fetches the
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

**`--dry-run` leaves a DRAFT now, and the approval is a row.** The run is created
when it is planned rather than when it is submitted, so the payload printed above
has an address: it can be opened in the app, edited — `studio runs edit`, or the
run page's own editor — and approved later with `studio runs approve`. Every edit
withdraws the approval and returns the run to `draft`. The approval records a hash of the plan and the ordered
images, and **the API refuses the submission if either has moved since** — which
is the "re-approve after any edit" sentence below, made mechanical. See
[RUN_PLAN.md](RUN_PLAN.md).

**Approval is of a payload, not of a plan.** A yes to "shall I render this?", an
answer to a multiple-choice question, or a payload shown earlier in the
conversation is not approval of the request about to be sent. Show it again and
wait. **There is deliberately no `--yes`-style flag on any generating command** —
`run`, `character turnaround` and `scenes board` all ask, and an approval flag
there is precisely the door an agent walks through while believing some earlier
exchange counted as approval. If one appears on a command that spends, it is a
bug.

`studio runs approve --relayed` is not that, and the distinction is the point:
it writes a *record*, it bills nothing, it still prints the whole payload, and
it marks the row `via: relayed` so a second-hand yes can be told from a typed
one. It exists because its absence was not a barrier — a pipe cleared the
confirm — and produced a row that overstated what had happened. See
[RUN_PLAN.md](RUN_PLAN.md).

### 2b. NEVER put an image into a character without approval

Runs are append-only history and descriptions can be rewritten, but a
character's **references** are who the character is — every later render is
verified against them, and every future generation may be driven by them.
Attaching, describing, regrouping or detaching one, or changing `default_set`,
is a decision that belongs to the user and is **separate** from having agreed to
spend money on a render.

So a successful generation does not become identity by itself.
`studio character turnaround` leaves every result in its run and prints the promotion
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
[THE RULE — S3 is the only origin](#the-rule--s3-is-the-only-origin) below;
enforced in code by `runs.py`.

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
        │                          `reports` for a module that raises, `die` for
        │                          one that finds the problem mid-function.
        │                          One `die`, where there were nine.
        ├── profiles.py            NAMED ENVIRONMENTS — which stack answers.
        │                          One resolver behind all five targeting
        │                          values; `--profile` selects, `dev` by default.
        ├── __init__.py            STUDIO_DIR, DEV_ENV_FILE, ENV_FILE, env_value
        │
        ├── adapters/              THE OUTSIDE WORLD — everything with a side effect
        │   ├── store.py           the media store, by path, through the API
        │   ├── api.py             one transport: token, refresh, library header
        │   ├── auth.py            Cognito sign-in + the token cache
        │   ├── s3.py              the AWS-login bridge — almost gone, see below
        │   ├── replicate.py       the HTTP client
        │   └── ffmpeg.py          probe / stitch / grab
        │
        ├── session/               who you are, and where you are pointing
        │   ├── commands.py        `studio login` / `logout` / `whoami`
        │   └── profile_commands.py  `studio profile` list / show / use / sync
        │
        ├── domain/                WHAT THINGS ARE — records and the tree's shape
        │   ├── paths.py           the one module that knows the key layout
        │   ├── runs.py  scenes.py  storyboard.py  movies.py  frames.py
        │   ├── projects.py
        │   ├── characters/       base.py profile.py refs.py pools.py rename.py cli.py
        │   ├── curate.py  contact_sheet.py
        │   ├── phrasebook.py  prompt.py
        │   └── templates/profile.yaml  reference_angles.yaml
        │
        ├── engine/                MODEL INVOCATION
        │   ├── resubmit.py        send a draft somebody already approved
        │   ├── runner.py          `studio run` / `studio models`
        │   ├── turnaround.py           `studio character turnaround` — the standard set
        │   ├── board.py           `studio scenes board` / `render` / `check`
        │   ├── registry.py  schema.py  submit.py  refs.py  add_model.py
        │
        └── objects/               raw object access
            └── upload.py  download.py  presign.py  convert.py
```

**`maintenance/` was a seventh subpackage and is gone.** It held the AWS-direct
one-shots — `catalog_check.py`, `catalog_gc.py`, `backfill_plans.py`,
`drop_fictional.py`, `confirm_outputs.py`, `ref_descriptions.py` — plus the
journal and derivations they shared, and `adapters/ddb.py` and `adapters/s3.py`
existed to give them clients. All of it is deleted. The migrations finished; the
orphan class `gc` swept is recorded by the API as a sweep row instead of being
searched for; and seeding moved to `studio/scripts/dev_seed/`, its own project,
because it is the one job that genuinely needs AWS clients. Nothing under
`adapters/` opens one now.

**Why the directories are named after what things ARE.** They used to be one
`store/` holding six unrelated kinds of thing — an S3 adapter, the key layout,
the record stores, an ffmpeg wrapper, four thin CLI verbs and two one-shot
migrations. "Store" described where bytes live, which was true of `s3.py` and
meaningless for a module that shells out to ffmpeg. Dependencies now point one
way: `cli` → `domain` → `adapters`.

**Why `src/`.** Without it, Python puts the working directory first on the
import path, so tests can pass against files that were never packaged. Both
`profile.yaml` and the angle spec are package data reached at runtime; a wheel
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
  Everything else needs **no AWS account at all** — the point of #308, finally
  true of the whole package now that `maintenance/` and both AWS adapters are
  deleted. This bullet said "required" flatly, then "required only for the
  maintenance commands"; the `aws configure export-credentials` bridge it
  described went with `adapters/s3.py`.
- **ffmpeg** — `brew install ffmpeg` — optional. The scene and movie code
  vendors `imageio-ffmpeg`; this is for checking a render by hand.

API keys:
- **REPLICATE_API_TOKEN** — https://replicate.com/account/api-tokens —
  **required**. Every engine runs on Replicate — video:
  `bytedance/seedance-2.0`, `kwaivgi/kling-v3-omni-video`, `google/veo-3.1`,
  `xai/grok-imagine-video`; image: `google/nano-banana-pro`,
  `google/nano-banana-2`, `openai/gpt-image-2`, `openai/gpt-image-1.5`.
  the registry served at `GET /api/models` is the list that is actually true.

  **Put it in `~/.config/andreas-services/studio/dev.env`**, the file that
  already holds this machine's dev pool password:

  ```
  REPLICATE_API_TOKEN=r8_…
  ```

  `studio/.env` is still read, and second — so a token already there keeps
  working, and moving it to the config dir takes effect without deleting
  anything. The order is what makes the move safe: the config dir wins, so a
  line left behind cannot quietly send the old token to Replicate.

  The reason to prefer the config dir is that `.gitignore` protects a secret
  from `git add` and from nothing else — not from `git add -f`, not from a
  copy of the working tree, not from a backup tool that indexes the repo. A
  credential outside the tree is out of reach of all three.

  **The token is deliberately not a profile field.** It is the same token
  wherever you are pointing, so scoping it per environment would be a knob with
  no meaning behind it.

  This paragraph used to end by saying the two stack pins `dev-setup.sh` writes
  (`STUDIO_S3_BUCKET`, `STUDIO_CATALOG_TABLE`) stay in `studio/.env` because
  they describe this checkout. They do not describe this checkout — the stack is
  per-machine and a second worktree got neither — and they are the profile's
  job now. An existing line still works and still wins when no profile is
  selected, which is why `dev-setup.sh` asks you to delete it.

Asset storage needs **neither an AWS login nor a key of its own.** Character
profiles, reference images and every generated asset live in S3 and never in
git, but the CLI reaches them through the API on the token `studio login` stored
and never names a bucket. Which bucket answers depends on where you are: locally
it is this machine's dev stack's, and `studio-prod-media-us-east-1` is the
deployed app's.

**This paragraph named the prod bucket as where local work stores things, and
that was wrong twice over** — the login is gone (#308) and the bucket is not
that one (#287). `studio/.env.example` says the same in the same words, because
this is the mistake that writes to production from a laptop. See
[`../infra/README.md`](../infra/README.md).

### The two trees — characters and projects

A **character** is an identity record. A **project** is a piece of work. They
used to be one folder, which left work involving two characters with nowhere to
live and work involving none borrowing a fake character called `misc`.

**A character and a project are ROWS, and each owns a folder.** The folder is
where their material lives; the record is what they are. Both folders sit
directly under the library root — there is no `characters/` or `projects/`
wrapper, because there is nothing left for one to group: an entity is found by
querying the table, not by listing a folder.

```
<character>/        a folder node the character's `root` names
    reference/      the images its REF# rows point at, in purpose subfolders
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
    angle/body/*.png    how to stand, for a turnaround
    angle/face/*.png     head-angle images
```

**`profile.yaml` and `project.json` are gone.** The bible is a validated map on
the character's row and the project's description is a field on its own; neither
was ever a document anyone edited as a file, and keeping them as files is what
made "who is this character" unanswerable without reading S3.

**The phrasebook is gone from this tree too** — it is `TERM#` rows, which is what
a per-model list of avoid/use pairs always was.

**The five folder names under a project and the four under a character are
convention, not schema.** The API creates them with the entity and resolves them
by name when it needs one, making it if it is absent. Rename `runs/` and the next
run makes a new one; every existing run is still reachable, because a run record
names its own folder node. Nothing breaks, and a folder someone makes by hand is
as real as the ones that came with the entity.

There is **no `media/` prefix** either — that went earlier, inherited from
mirroring Google Drive 1:1.

**None of these names appears in an S3 key.** A key is
`<characters|projects|libraries>/<entity id>/<node id>.<ext>`, stamped once when
the node is created and never parsed. The tree above is the catalog's; the
bucket holds bytes under ids.

### HISTORICAL — the `media/<owner>/` tree, and the move off it

Nothing in this section describes anything that still runs. It is kept because
the *shape* of the old tree is not recoverable from anywhere else: the source
bucket was deleted in August 2026, and `studio migrate-layout` — the five-phase
command that did the move, and `paths.classify()` / `paths.relocate()`, the map
it moved by — were deleted once the owner confirmed no `media/`-layout tree
survives. What it moved is history; **why each folder became what it became** is
still the reason the current tree is shaped the way it is.

The old tree had exactly one axis, the **owner**, and everything hung off it.
The move split that axis in two: an owner became both a **character** (who
someone is) and a **project** (work someone did), which is the distinction the
section above is entirely built on.

| Old | New | Why |
|---|---|---|
| `media/<owner>/profile.yaml` | `characters/<owner>/profile.yaml` | identity |
| `media/<owner>/reference/…` | `characters/<owner>/reference/…` | identity |
| `media/<owner>/input/<owner>_in_<n>.<ext>` | `characters/<owner>/reference/…` | **generated** character imagery |
| `media/<owner>/input/…` (everything else) | `characters/<owner>/corpus/…` | **raw uploads** |
| `media/<owner>/originals/…` | `characters/<owner>/seed/…` | the founding real-world photos |
| `media/<owner>/other/…` | `characters/<owner>/corpus/…` | collected material |
| `media/<owner>/trash/…` | `characters/<owner>/archive/…` | retired, not deleted |
| `media/<owner>/favorites/…` | `projects/<owner>/favorites/…` | a keeper is **work**, not identity |
| `media/<owner>/runs/…` | `projects/<owner>/runs/…` | work |
| `media/<owner>/scenes/<id>/parts/part-NN.<ext>` | `projects/<owner>/scenes/<id>/shots/shot-NN.<ext>` | a "part" is a **shot** |
| `media/<owner>/scenes/<id>/…` | `projects/<owner>/scenes/<id>/…` | work |
| `media/<owner>/chains/…` | `projects/<owner>/chains/…` | work |
| `media/phrasebook/…` | `phrasebook/…` | shared — belongs to no owner |

Three of those rows are the ones that carried judgement rather than a rename:

- **`input/` split in two, on the filename.** One folder held both material a
  person uploaded and imagery the harness had generated of the character —
  generated frames lived in the input pool only to stay under the engines'
  reference caps. Generated frames are *reference*; uploads are *corpus*. The
  test was a filename shape, `<owner>_in_<n>.<ext>`.
- **`favorites/` crossed from the character tree to the project tree.** Marking
  an output a keeper says something about the work, not about who is in it.
- **`parts/part-NN` became `shots/shot-NN`.** The vocabulary change was made in
  the object names as well as in the code, so nothing was left reading "part"
  in one place and "shot" in another. `scene.json` was rewritten to match —
  `parts` → `shots`, `part_key` → `shot_key`, `uniform_parts` →
  `uniform_shots` — which is what the rewrite phase below was for.

**The `input/` rule was already half-hollow when it was deleted, and the record
would mislead without this.** The turnaround test was a filename regex *or*
membership of a set of named generic sheets — and that set had already been
emptied. A generic anatomy sheet used to be listed in it, which sent it to
`reference/`, where it was indexed as identity and tagged `body`; `--pick-tag
body` could then hand a model a stranger's sculpt as one of the character's own
reference angles. Generic guide material is **config**: it lives in the repo and
is copied to `config/angle/`, and never into a character. So by the end only the
regex ever fired, and the "or a named sheet" half of the rule matched nothing.

**Five phases, each its own invocation, and the ordering was the safety
property.** Not five steps behind one switch — separate commands, every one a
dry run unless given `--apply`:

    plan     what would move, grouped by rule. UNMAPPED had to be 0.
    copy     server-side copy old -> new. Idempotent; skipped what was there.
    rewrite  patch the S3 keys recorded INSIDE the copied documents.
    verify   every destination exists, and every key any document names resolves.
    delete   remove the originals. Refused unless verify had passed.

Nothing was rewritten before everything was copied, and nothing was deleted
before everything was verified. Splitting the phases into separate invocations
is what made that ordering something a person had to step through rather than
something a flag could skip.

Two details are worth keeping:

- **The rewrite phase was not cosmetic.** A run record holds S3 keys, not URLs
  — that is the point of `runs.check_bindings` — so moving objects without
  patching the records would have left every recorded run pointing at keys that
  no longer existed, and chaining from history would have broken. This is the
  same rule stated elsewhere as *moving an object means rewriting the records
  that name it* — which was true for as long as a record named a path.
  `domain/rewrite.py` existed for it and is deleted: a record names a node id,
  so nothing a move touches can be stranded.
- **`verify` separated breakage it had caused from breakage it had inherited.**
  Curation had renumbered and removed reference images after the runs that
  cited them, so some records already pointed at keys that were gone. A
  reference to something that was never a destination was already broken;
  reporting those separately is what stopped inherited breakage from blocking a
  migration that did not cause it.

**A note on what this would do if it were still here.** It predated the
catalog. It had no DynamoDB import at all, so it was unaware that every object
in the bucket is now a row's `blob_key`: its `copy` and `delete` phases would
move objects out from under the catalog rows, and its `rewrite` phase would
patch JSON documents without touching a single row. That is the other half of
why it went.

**`config/` is the one tree whose source of truth is the repo.** It lives at
`studio/config/`, and `dev-setup.sh` syncs it out (`--size-only`, never
`--delete`). The bucket holds a copy because a model may only be handed a
presigned URL of an S3 object — an angle image that was never synced cannot be used, so
`turnaround` checks for them and says to re-run the script. Editing an angle image in the
bucket rather than the repo is how they diverge.

**`phrasebook/wording.yaml` is seeded from the repo and then owned by the
bucket**, which is a different rule and lives beside it in
`scripts/dev-shared-material.sh`. `studio/phrasebook/wording.yaml` is a starting
copy and `dev-setup.sh` puts it in **only when the key is absent**: from the
first `studio phrasebook add` the bucket's copy is the live document, so a sync
would delete recorded entries. It is copied at all because `PATCH /api/text`
overwrites and never invents, which left `add` permanently broken on a fresh dev
stack (#425).

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

**A run is a row with a folder.** The envelope — status, model, prediction id,
timings, cost, bindings, outputs, lineage — is `RUN#<id>`/`META`, and it is
studio's to validate and query. The provider's own documents stay bytes:

```
<project>/runs/<run id>/                          the folder the record names
    request.json    what we sent, verbatim        ─┐  payload blobs.
    prompt.json     the prompt source, when used   ├─ studio stores these
    result.json     what came back, verbatim      ─┘  and decodes none of them
    output/         the artifact(s) — .mp4, .jpg, however many
```

That split is the point. The pipeline changes the payload's shape freely, so
nothing may parse it; but "which runs used this character, on which model, and
what did they cost" is a question about studio's own bookkeeping, and it now has
an answer. **`bindings` are node ids**, so a run that consumed an image still
resolves it after that image is renamed or moved.

A run belongs to a project and **names the characters it used**, inferred from
its bindings rather than trusted from the flags — written as `RUN#`/`CHAR#` rows,
which is what makes `studio runs find --character <name>` one query rather than
a walk over every project's every run folder.

The folder name still starts with a timestamp, which is convenient when browsing
and is not an id: the run's id is a UUID and nothing derives one from the other.

A **scene is keyed by its slug** and created before anything renders — it is
the plan as much as the record. A **movie** still takes the run id shape,
because a movie is only ever a finished cut:

```
<project>/scenes/<slug>/
    storyboard/     the panels: shot-<NN>-p<M>.png
    shots/          each source clip, copied in, numbered in cut order
    output/         the stitched scene — <slug>.mp4

<project>/movies/<YYYY-MM-DD_HH-MM-SS>_<slug>/
    scenes/         each scene's output, copied in, numbered in cut order
    output/         the finished movie — <slug>.mp4
```

`scene.json` and `movie.json` are gone the way `profile.yaml` went: a scene is
`SCENE#<id>`/`META` with one `SHOT#` row per planned shot, and a movie is its
own record naming scenes in cut order. A shot's `order` is an attribute, so
revising a plan moves rows rather than rewriting a document.

Both are **derived, never a source of truth**: the runs they name remain the
history, so either can always be rebuilt. Sources are copied in server-side so a
scene stays playable as its runs accumulate around it, and each manifest records
the originating ref beside the copied key — copying does not lose lineage. Both
stitch through the same function — `adapters/ffmpeg.py`'s `stitch()`, which
stream-copies when the
inputs already agree on codec, geometry, frame rate and audio layout, and
re-encodes (recording that it did) when they don't.

### Identity vs working material — never conflate them

A character's **reference set** is a library of generated character imagery,
grouped by purpose and described one `REF#` row at a time.
The engines cap what they accept (Kling 7, Seedance 9, Nano Banana 14) and send
it in full, so a *subset* is chosen deliberately — `--pick`, `--pick-tag`, or
the character's `default_set`. An over-cap selection is **refused**, with the
index printed, rather than truncated: which images a generation saw should not be
decided by whatever a folder listing returned. The API resolves the selection
(`GET /api/characters/<id>/selection`), so the CLI and the app cannot disagree
about what a model was shown.

A project's `input/` pool is the **working pool** — uploads and frames pulled
off clips to drive the next generation. Uncapped, picked from by number
(`--input N`), never identity.

**A frame pulled off a run goes to the project pool.** Promoting one into a
character's `reference/` feeds model output back in as identity and compounds
drift; it is a deliberate curation decision, and it should be described when it
happens.

**Moving an object means rewriting the records that name it.** Run records,
scene and movie manifests and chains all store S3 keys, so a move invalidates
every document that cited it — **and this is the paragraph the entity model
retired.** Records name node ids, so a move invalidates nothing and there is
nothing to carry along. It is kept because the failure it describes is the one
this whole change exists to make impossible. Curating without
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

All eighteen live in `studio/.claude/skills/` and are discovered as
`studio:<name>` — directory-scoped, so they surface when the work is under
`studio/`. Seventeen are `studio-media-*` and one is `studio-code-*`; `ls` that
directory rather than trusting this number, which three docs have disagreed
about before.

| Skill     | What it does                                              |
|-----------|-----------------------------------------------------------|
| `studio-media-scene`     | **A piece longer than one generation.** Chains video runs — each starting from the previous clip's last frame — then stitches them into one cut. Owns the chain loop, the continuity rules that keep shots cutting together, the per-shot verification gate, and the `multi_prompt`-cuts-vs-timing trade. Use when a shot outruns the model's duration ceiling or must read as one continuous take |
| `studio-media-movie`     | **The tier above a scene.** Cuts a project's finished scenes into one piece. Owns the cut order and the movie-vs-longer-scene decision: cut a movie where a hard cut belongs (a change of place, time or subject); extend a scene where it must read as one take |
| `studio-media-shot`      | **Orchestrates a whole shot**: reads a brief, shows the multi-step plan as JSON for approval, then renders a still and animates it — frame-first, one approval gate per billing step. Use when a brief describes motion or spans more than one studio-* call |
| `studio-media-core`      | **The shared machinery.** The model **registry** (the backend's `models.json`, served at `GET /api/models`), the one submit lifecycle, live-schema validation, and `studio run` — the runner that invokes *any* registered model. Models are DATA, not code |
| `studio-media-add-model` | **Onboard a new Replicate model**: reads its live schema *and* its README, proposes a registry entry for review, then writes it to the registry. Also owns writing the new model's skill page — nothing generates it. The only way a model should be added |
| `studio-media-image`     | The **frame-first workflow** for stills — why to render a frame before a video, run chaining, the approval gate, choosing between the image models. Model-agnostic; each model has its own skill |
| `studio-media-nano-banana-pro` | `google/nano-banana-pro` — strongest all-round image model. Legible text, 4K, ≤14 refs, tunable safety filter. **Never set `allow_fallback_model`** — it reroutes to a different model than the one approved |
| `studio-media-nano-banana-2` | `google/nano-banana-2` — fast/cheap sibling. The only model with the extreme `1:4`…`8:1` ratios; Google Search / Image Search grounding |
| `studio-media-gpt-image-2` | `openai/gpt-image-2` — OpenAI's newest, and **the default for character frames**. Dense legible text, pixel-exact sizes, references held at high fidelity **automatically**. No transparent background |
| `studio-media-gpt-image-1-5` | `openai/gpt-image-1.5` — the one that does **transparent backgrounds** and exposes `input_fidelity` (dial face preservation up *or down*). Aspect limited to `1:1`/`3:2`/`2:3` |
| `studio-media-seedance`  | `bytedance/seedance-2.0` — native audio, first/last frame, reference images/videos/audio. A start frame and a reference set **cannot** be combined |
| `studio-media-kling`     | `kwaivgi/kling-v3-omni-video` — Kling 3.0 / O3 Omni (~$0.168/s, `reference_images` for consistency, native multi-shot to 6 cuts). Start frame and reference images can be combined |
| `studio-media-veo-3-1`   | `google/veo-3.1` — the control-oriented engine, and the only one with a repeatable **seed** and a real `negative_prompt`. Reference images work only at 16:9 and 8 seconds; durations are a 4/6/8s enum |
| `studio-media-grok-imagine-video` | `xai/grok-imagine-video` — animates one approved still, any integer 1–15s, and is the only registered model that **edits an existing clip**. No reference images, so not for holding a character on-model |
| `studio-media-prompt`    | Author prompts as structured JSON for either engine (`--engine seedance\|kling-replicate`); validates rules and routes technical fields + the negative prompt where each engine takes them |
| `studio-media-character` | Manage on-model characters (create/update/list/curate/load) whose bible is a field on the character's row and whose reference library is `REF#` rows; characters are data, not skills |
| `studio-media-s3`               | Address the media store through the API by name path (list, upload, download, presign) — the asset store holding **characters** and **projects**, plus the shared **run store** (`runs.py`), **scene store** (`scenes.py`) and **movie store** (`movies.py`), the project registry (`projects.py`) and the slug/address helper (`paths.py`). Storage only; model invocation lives in `studio-media-core` |
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
`pipeline/tests/contracts/cli_surface_reference.json` records what argparse exposed —
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

The package is `studio/pipeline/src/studio_pipeline/`, in six subpackages plus
three modules at its root.

**At the root.** `cli.py` is wiring and nothing else. `errors.py` turns a domain
failure into `error: …` and exit 1. **`profiles.py` decides which stack an
invocation is talking to** — the five targeting values, the file they live in,
and the order they resolve in. Read its docstring before changing anything that
reads a bucket, a table, an API URL or a pool id: the resolution order is not
symmetric, and both directions are deliberate.

**`adapters/` — the outside world.** Nothing here knows about characters, runs
or projects.

| Module | Purpose |
|---|---|
| `store.py` | **The media store, addressed by path and reached through the API.** Resolve a name path to a node, list its files in natural order, read, write, upload, copy, presign, and ensure a folder exists. No bucket name, no credentials — bytes travel to S3 directly on presigned URLs the API signs, which is what keeps a video out of the Lambda's request limit. `s3.py` is being retired into this. |
| `api.py` | One transport for every call the CLI makes: bearer token, refresh-on-401, library header, error mapping. Decided once so no caller re-decides it. |
| `auth.py` | The Cognito sign-in behind `studio login`, and the token cache it writes — **keyed by profile**, so a prod session and a dev session coexist instead of one overwriting the other for every shell on the machine. Its `DEFAULT_API_URL` is deleted: unset is a refusal, not a silent connection to production. |
| `s3.py` | **Deleted.** It was the boto3 session every AWS-direct caller asked for, and its callers — `adapters/ddb.py` and the three `maintenance/` modules that reconciled the bucket against the table — are deleted too. The one thing that outlived it is a plain boto3 session for `profile sync`, which lives in `profiles.py` as `aws_session()` because that is its only caller. |
| `ddb.py` | **Deleted**, with the six `maintenance/` commands that were its only callers. The marshalling it held — floats to `Decimal` on the way in, `Decimal` to int recursively on the way out, each paid for by a real failure — travelled to `scripts/dev_seed/dev_seed/aws.py`, which is the one tool left that writes DynamoDB directly. |
| `replicate.py` | Token, HTTP, download, poll. |
| `ffmpeg.py` | Probe, stitch, frame grab, contact grid. A scene and a movie join their inputs by identical rules because they call the same function. ffmpeg ships in the wheel; no system install. |

**`session/` — who you are, and where you are pointing.** `commands.py` is
`studio login` / `logout` / `whoami`; everything the CLI knows about identity it
reads back off the stored token. The acceptance test for the whole of #308 is
that these work on a machine with **no AWS credentials configured at all**,
which is why `adapters/auth.py` builds an unsigned Cognito client —
`InitiateAuth` needs no AWS identity, but boto3 resolves the credential chain at
construction and would fail first.

`profile_commands.py` is `studio profile list` / `show` / `use` / `sync`. It is
in the same subpackage because the two questions are one in practice: a session
belongs to a profile, `login` signs you in to the one in force, and `whoami`
prints it first. `sync` is the only member that needs AWS — it reads a dev
stack's Terraform state or prod's SSM parameters, so that no id is ever typed
into a config file by a person.

**`domain/` — the tree and the records in it.**

| Module | Purpose |
|---|---|
| `paths.py` | **Slug rules, the starting layout names, and address joining — and nothing else.** It was 334 lines of key construction whose only job was making twelve modules spell `characters/<slug>/…` identically, and it is a name checker now. An entity record names its own nodes, so nothing builds a path to assert where something must be. |
| `projects.py` | Project CRUD through the entity routes, plus the **input pool**. `require_project()` turns a missing `--project` into an error that lists the real options. Creating a project is one call: the API writes the record, the slug claim, the root folder and the starting subfolders in one transaction, so there is no half-made project to recover from. |
| `runs.py` | The shared **run store** every engine records into: the envelope, output uploads, runref resolution for chaining, `find --character` across projects — which is one API query now rather than a walk over every project's every run folder. It refuses a URL-shaped binding, and so does the API; keeping the check here as well is what makes a `--dry-run` refuse before anything is sent. |
| `scenes.py` | The **scene store**: a piece planned, shot and cut, under `projects/<p>/scenes/<slug>/`. Owns the manifest, `assemble`, `handoff`, and the read-only half of the CLI. Writing a manifest ensures the scene's folder — `new_scene` writes one for a scene that has never existed, and the catalog has no folder until something asks for it. |
| `storyboard.py` | **The plan document**, pure data: what a shot's panels mean, which one is the start frame once the chain has spoken, how a revision merges onto work already paid for. No S3, no models — so the rules that decide what a shot sends are testable on their own. |
| `movies.py` | The **movie store**: scenes cut into one piece. The same shape one tier up, including the folders a cut needs. Copying a scene in is a read plus a write rather than a server-side `CopyObject`; see `store.copy` for why one blob under two rows is not on offer. |
| `frames.py` | Stills out of a run's video — the handoff frame, and the contact grid that lets a clip be looked at before more money is spent on it. Its `chain` store is for a sequence with no scene behind it; a planned scene derives its own frames from `scene.json`. |
| `characters/` | The character record, in four modules. `base` — names, pools, node helpers. `profile` — the bible: schema, and the `edit` local round trip whose conflict check is a `rev` sent with the write, so the API refuses a stale push itself. That was the S3 ETag, then the node's `updated_at`, and both were check-then-write with a gap; `rev` is compare-and-swap and closes it. `refs` — the `REF#` rows: attach, describe, order, regroup, detach, and the selection the API resolves. `pools` — corpus/seed/archive, material rather than identity. `cli` assembles the group; commands are `@click.command` and registered there, which is what keeps the package acyclic. **`rename.py` is gone** — a rename is one `PATCH`, because the slug is an attribute rather than a path segment. |
| `curate.py` | The pool operations that go wrong by hand — `dedupe`, `groups`, `move`. **`renumber` and `regroup` are deleted**: order and group are attributes on a `REF#` row, so there are no holes to close and regrouping writes no object. `move` is the one worth knowing — when a byte-identical copy is already in the destination it deletes the source instead, which is the one path here that removes an image. |
| `curate.py` | Pool maintenance — dedupe, move, groups. **`digest` is a dictionary read now**: the API records the MD5 of every object when it confirms the upload (S3 hands it back as the ETag of a single PUT), so comparing two images is comparing two served values. It used to download each same-size candidate over HTTPS, which made hashing a forty-image pool to find nothing forty downloads. |
| `prompt.py` | **Reading the object and printing the answer, and nothing else.** The rules — one camera move per shot, no bare "fast", no camera verbs in the action, the beat budget, the start-frame redundancy warning — are `backend/studio_core/services/prompt.py` and reachable at `POST /api/prompt`. They needed the registry and the phrasebook, both of which are the API's, and while they lived here nothing but `studio prompt` could run one of them: the SPA could offer no checking at all. 690 lines → 157. |
| `phrasebook.py` | Per-model wording lists, as `LIB#`/`TERM#` rows. It was a YAML document in the bucket with no catalog node, which is why it was read by raw key and written by an overwrite that could not invent the file — so `phrasebook add` failed outright on a library that had never held one. A row has no such state: the first `add` writes the first term. |
| `contact_sheet.py` | Labeled thumbnail grids over arbitrary keys. The character-pool half walks the pool **recursively**, like `characters/refs`: `reference` is the default and holds group folders rather than images, so a one-level listing would report the commonest invocation as an empty pool. Each tile's local name carries its group, because `face/<name>_1` and `body/<name>_1` share a basename and collided in one directory. |

**The duplicate-submission guard is a query, and `engine/ledger.py` is deleted.**
It kept a fingerprint of model, inputs and bound images per profile beside the
credentials file, so `run` could refuse a payload it had already paid for — local
rather than a query because the listing rows are a deliberately small projection
and did not carry the payload, making a server-side comparison one
`GET /api/runs/<id>` per candidate, ~1800 requests before the first submit of a
72-image batch.

Its own docstring named the fix: project the fingerprint onto the listing row and
filter on it. `catalog.submission_fingerprint` derives one from `plan_digest` —
which already hashes the plan and the ordered sends — plus the model, so there is
no second hash to keep in step. `GET /api/runs?fingerprint=` is one query.

Two consequences worth knowing. It now catches what a per-machine file never
could: a second machine, and a colleague. And the check moved to *after* the
draft is created, because the draft is what carries the fingerprint — the CLI
reads the value rather than computing it, which is the whole point in a
repository where `plan_digest` once had three implementations and one of them
silently disagreed. A draft costs a row and no bytes, so the check is still free,
and the never-billed states are excluded so an abandoned draft cannot make the
next identical payload look like a duplicate.

**`engine/` — invoking a model.**

| Module | Purpose |
|---|---|
| `registry.py` | **Reads the registry, over the wire.** `GET /api/models` via `adapters/entities.models`, memoised once per process. The file itself is `backend/studio_core/models.json` — it moved so the API and the SPA could measure a reference selection against the same entries the CLI does, which `ENGINE_CAPS` (three families of nine) had been standing in for. |
| `registry_file.py` | **Writes it.** The repo file, for the only two commands that edit it — `add-model` and `models refresh`, both of which are really asking Replicate what a model accepts. Separate from the reader on purpose: reading works against any environment, writing is a reviewed repo change that reaches production on deploy. |
| `registry.py` | Load / look up / list; snapshot saving for refreshes. |
| `runner.py` | `studio run` — builds the payload and invokes *any* registered model. |
| `submit.py` | The one submit lifecycle, image and video alike. |
| `schema.py` | Live schema fetch; validates fields, enums, ranges, `denied`. |
| `refs.py` | Character reference selection and project input pool → S3 keys. |
| `turnaround.py` | `studio character turnaround` — the STANDARD reference set, one run per angle in `domain/templates/reference_angles.yaml`. Reads the character's bible for the prompt, binds an angle image from `config/`, then files, describes and indexes each result. Lives here rather than in `domain/` because it invokes models; it drives the same lifecycle as `runner.py` rather than repeating it. |
| `board.py` | `studio scenes board` / `render` / `check` — the two commands that spend money in a scene's life, plus the free one that says whether they would work. Turns the plan's roles into bindings and hands them to the same lifecycle `runner.py` drives. Every cap, exclusion and format rule stays in `submit.py`; a copy here is the one that drifts. |
| `add_model.py` | Onboarding: fetch schema + README, infer an entry, append it to the registry. It writes no documentation — see `studio-media-add-model`. |

**`objects/` — moving bytes.** `upload.py`, `download.py`, `presign.py`
(how assets reach Replicate), `convert.py` (re-encode so a target engine accepts
it) and `crop.py` (cut a rectangle out of one). `convert` writes into the
project input pool through `projects.add_inputs` rather than repeating its
numbering, staging the converted bytes to a temp file because that function
takes local paths; `--dest-key` ensures the destination folder first, since the
catalog has no folder until something asks for one. **`upload` ensures its
`--folder` for the same reason** — it did not, so the first file into a new
subfolder failed on a missing parent while `convert` in the next command
succeeded, and nothing in the CLI created a folder at all. `crop.py` reuses
`convert`'s source resolution, format table and destination handling; what is
its own is the box parser and the clamp, where every error message names the way
the box was wrong — `LEFT,TOP,WIDTH,HEIGHT` instead of `LEFT,TOP,RIGHT,BOTTOM`
being the commonest. It deliberately contains no subject detection: that is
platform work, and a wrong box is worse than no command.

**`maintenance/` — deleted, all of it.** This section used to describe eleven
commands in various states of finishing. They are gone, and what replaced each is
worth recording because the replacements are not all the same kind of thing.

*The migrations finished.* `backfill_replicate.py`, `migrate_layout.py` and
`catalog_seed.py` were already deleted. `catalog_check.py` (`catalog verify` /
`reseat` / `edges`), `backfill_plans.py`, `drop_fictional.py`,
`ref_descriptions.py` and `confirm_outputs.py` join them: prod carries its 39
character records, every run has a plan, the dead attribute is swept, captions
live on nodes, and the outputs are confirmed. A one-shot that has run is not a
tool; keeping it is keeping a permanent hole cut for a job that is over.

*The orphan class was fixed at the source.* `catalog_gc.py` listed every object
in the bucket and scanned every row in the table to find blobs nothing named. It
existed because `delete_node` removed rows, handed the caller the keys, and threw
away the only list of what was in flight. The API keeps that list now —
`catalog.open_sweep` writes it to a `SWEEP#` row *before* the rows go,
`manage.release` closes it once the bytes are gone, and `manage.drain` finishes
any sweep an earlier request abandoned, rechecking each node so a crash between
open and delete cannot collect bytes a live row still names. The leftover is
addressed instead of searched for, so there is nothing to sweep and no command to
run. See `backend/studio_core/services/manage.py` and
`backend/tests/unit/test_sweeps.py`.

*Verification went with it.* `catalog verify` caught eighteen classes of
disagreement, and most of them were damage from the migration it was checking.
Two were live — `stale_plan_digest` and `incomplete_row` — and nothing replaces
them; that is a deliberate trade rather than an oversight, and if either starts
happening the answer is a check inside the API rather than a CLI command holding
a table scan.

*Seeding became its own project.* `dev_seed.py` and `derive.py` moved to
`studio/scripts/dev_seed/`, invoked as `dev-seed` and wired into
`scripts/dev-aws-seed.sh`. It is the one job that genuinely needs AWS clients —
it writes the rows and copies the blobs a library is *made of*, before there is a
session or often a library — and keeping it in the CLI is what kept
`adapters/ddb.py` and `adapters/s3.py` alive for everything else to shelter
under. Its `pyproject.toml` carries that argument.

`maintenance/journal.py` went with the two commands that journalled, and nothing
in the package writes `local/migrations/` any more.

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
   restructure is what actually breaks this code. **Do not stub Replicate in
   it** — `conftest.py` sets `STUDIO_REPLICATE_MODE=fake` autouse and
   `adapters/replicate.py` answers locally, with an autouse socket guard behind
   that for anything reached indirectly. See `studio-code-pipeline`.
7. Document it in the table above, and in `studio/CLAUDE.md`.

To add a new *model* rather than a new skill, use `studio-media-add-model` — models
are data in the registry, not code. That skill also writes the new model's page;
`studio add-model` deliberately generates no documentation.
