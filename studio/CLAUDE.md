# Claude Instructions – studio

**Read the hard rules below before doing anything else in this directory.** They
are not preferences, and two of them are about spending money and leaking
identity. Everything else in this file is an index.

## What studio is

Studio is one service with two halves that share one S3 bucket.

| Half | Where | Runs | Doc |
|---|---|---|---|
| **The pipeline** — makes the media | `pipeline/` (code) + `.claude/skills/` (docs) | Locally, inside Claude, under your own AWS login. **Never deploys.** | [docs/PIPELINE.md](docs/PIPELINE.md) |
| **The app** — browses the media | `backend/`, `frontend/` | `studio.andreas.services` + `studio-api.andreas.services`, deployed by CI | [docs/WEB_APP.md](docs/WEB_APP.md) |
| The bucket both use | `infra/modules/media` | `s3://xharness-prod-media-us-east-1/` | [infra/README.md](infra/README.md) |

That split is unusual for this monorepo, where a service directory is normally a
deployable unit and nothing else. It is deliberate: the tools that produce the
library and the app that reads it were separate repos until August 2026, and
keeping them apart meant the rules below were invisible to anyone working on the
app. **A change under `pipeline/`, `.claude/skills/` or `docs/` deploys
nothing** — the CI path filters exclude all three.

The pipeline is one package exposing one command. `studio --help` lists every
subcommand; `scripts/dev-setup.sh` installs it and puts it on PATH.

The bucket name is grandfathered from that era and does not follow the repo's
naming convention. It is not an oversight; see
[infra/modules/media/variables.tf](infra/modules/media/variables.tf).

---

## Hard rules

These hold everywhere in this directory, in every skill, and in anything written
back to it. Full statements and reasoning in
[docs/PIPELINE.md](docs/PIPELINE.md#hard-rules).

### 1. NEVER name a character anywhere in the repo

No character name appears in this repository — ever. Not in code, docstrings,
`SKILL.md` files, examples, comments, tests, fixtures, commit messages, branch
names, or PR titles and bodies. Characters are **data**, living in S3 under
`characters/<name>/`. The repo describes the machinery that operates on any
character; use the `<name>` / `<project>` / `<slug>` placeholders.

### 2. NEVER submit without approval of the FULL payload

Every generation costs money. Before any submit, show the complete `input`
object as two JSON documents — `PROMPT` then `INPUT` — and get explicit
approval. Re-approve after **any** edit. `--dry-run` renders exactly this
without billing.

### 3. S3 is the only origin

Assets are never uploaded to a model provider. Anything sent to a model must
already be an S3 object and reaches Replicate only as a short-lived presigned
URL. This is enforced in code: `runs.py` refuses a URL-shaped binding.

---

## LOCAL RUNS AGAINST PROD. THIS IS DELIBERATE.

Studio has **one environment**, and both halves of local development point at
it. `studio <command>` reads and writes the live media bucket. `dev-up.sh`
serves the app from localhost against that same bucket, signing in to the
**live** Cognito pool. There is no dev bucket, no dev pool, no seed data.

That is a real departure from every other service in this monorepo, and it is
on purpose: studio is a view onto one library of generated media. A second,
empty bucket would exercise none of the behaviour that matters — the listing,
the sorting, the reel, the tidy-up all only mean anything against real
material — and keeping two copies of ~700 MB in sync would be its own failure
mode.

**What follows from it, and what you must hold in your head:**

- **A `delete` you run locally is a delete in production.** So is a rename, a
  move, and a `curate` pass. There is no undo prompt beyond the one the command
  itself gives you.
- What makes that survivable is not care, it is the bucket: versioning is on,
  and neither the API role nor your own commands are granted
  `s3:DeleteObjectVersion`. Every delete is a tombstone, so it is recoverable.
  Do not "tidy up" that grant.
- `scripts/dev-setup.sh` writes `frontend/.env.local` and pins the bucket in
  `.env`, reading both from SSM — the values the deploy workflow wrote from
  Terraform's outputs, so local cannot drift from what is deployed. Re-run it
  rather than editing either file.
- The one thing that is genuinely local is the **API**: `dev-up.sh` runs Flask
  on `:8000` and the SPA points at it, so backend changes are tested locally
  against real data before they reach the Lambda.

---

## Which skill

Fifteen skills, discovered as `studio:<name>`. Start here, then read that
skill's own `SKILL.md`.

| You want to | Use |
|---|---|
| Store, fetch, list or presign anything; record a run | `studio-s3` |
| Make a still image | `studio-image`, then a model skill |
| Make one shot end to end (still → motion) | `studio-shot` |
| Continue past a model's duration ceiling | `studio-scene` |
| Cut finished scenes into one piece | `studio-movie` |
| Work with a recurring character | `studio-character` |
| Write a tight, repeatable video prompt | `studio-prompt` |
| Invoke a model generically, or inspect its schema | `studio-core` |
| Register a new Replicate model | `studio-add-model` |
| Pick a video engine | `studio-seedance` · `studio-kling` |
| Pick an image engine | `studio-nano-banana-pro` · `studio-nano-banana-2` · `studio-gpt-image-2` · `studio-gpt-image-1-5` |

**Ask which project before generating anything.** Work is addressed as
`projects/<project>/`, and guessing puts runs somewhere nobody looks again.

---

## Conventions that bite

- **`SKILL.md` files are documentation; the code is in `pipeline/`.** A skill
  directory holds prose and nothing else. Adding a command means adding a module
  under `pipeline/src/studio_pipeline/` and an entry in `cli.py`, then
  describing it in the relevant `SKILL.md`.
- **A skill describes the CLI surface and never names a module, path or
  function.** The internals are documented once, in
  [docs/PIPELINE.md](docs/PIPELINE.md#the-modules), next to the code they
  describe. Two skills used to carry module tables and five of those names
  rotted into files that no longer existed — prose about code only stays true
  when it lives beside the code. `pipeline/tests/test_docs_match_cli.py` fails
  the build on a module name in a skill, on a `studio …` line that names no real
  command, and on a broken link.
- **No code in this repo generates prose.** `studio add-model` writes the
  registry entry and stops; `studio-add-model` writes the model's page. The
  generator it replaced emitted boilerplate around a `TODO` asking for the only
  part worth reading, and quietly rotted for months.
- **One constant knows where `studio/` is**: `studio_pipeline.STUDIO_DIR`. Use
  it rather than counting `".."` segments — that is what broke every time a file
  moved.
- **Claude Code does not read a nested `settings.json`.** New Bash permissions
  for these skills go in the **monorepo root** `.claude/settings.json`, even
  though the skills do not.
- **One package, one dependency set** (`pipeline/pyproject.toml`, locked in
  `uv.lock`). Run `scripts/dev-setup.sh` once — the session hook does it for
  you — and `studio` is on PATH.
- **`--help` is not a test.** Every subcommand printed usage happily while
  `engine/refs.py` referenced an undefined name, and again while every
  `character`/`curate`/`run` subcommand had no handler to dispatch to — usage
  never reaches either. `pipeline/tests/` covers wiring and *execution* for
  that reason, and runs on PR even though the pipeline deploys nowhere.
- **The CLI surface is a contract.** `pipeline/tests/cli_surface_reference.json`
  records every option, arity, default and help string. Changing the CLI means
  regenerating it deliberately — never editing it to make a test pass.
- **`terraform destroy` on `studio/prod` fails by design.** The media bucket
  carries `prevent_destroy`; see [infra/README.md](infra/README.md).
- **Moving an object means rewriting the records that name it.** Skipping that
  step is what once left 69 records pointing at reference images that no longer
  existed — `rewrite.py` exists for this.
- The app's API takes the **ID token**, not the access token; the run JSON is
  deliberately served as text and never parsed. More in
  [docs/WEB_APP.md](docs/WEB_APP.md#conventions--gotchas).

## Local development

```bash
studio/scripts/dev-setup.sh   # the pipeline half — installs uv, warms caches
studio/scripts/dev-up.sh      # the app half — backend :8000, frontend :5173
```

Both need a live AWS login (`aws login`). Note the credential split the root
[CLAUDE.md](../CLAUDE.md) documents: the AWS CLI reads its own login cache,
boto3 and the Terraform provider do not, so export before running Terraform:

```bash
eval "$(aws configure export-credentials --format env)"
```
