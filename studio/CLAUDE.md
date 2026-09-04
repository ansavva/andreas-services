# Claude Instructions – studio

**Read the hard rules below before doing anything else in this directory.** They
are not preferences, and two of them are about spending money and leaking
identity. Everything else in this file is an index.

**The data model is [docs/ENTITY_MODEL.md](docs/ENTITY_MODEL.md)**, worked
through one character and one project in
[docs/ENTITY_MODEL_EXAMPLE.md](docs/ENTITY_MODEL_EXAMPLE.md). Characters,
projects, runs, scenes and movies are rows with UUIDs; the folder tree hangs off
them; S3 keys and entity root folders carry ids, never names. Read it before
assuming a name is an address or that a document defines anything.

**A run has an authored half — [docs/RUN_PLAN.md](docs/RUN_PLAN.md).** It is a
`draft` from the moment it is planned, carrying a `plan` and one `SEND#` row
per bound image, and it stays a draft until a person says to send it. **There
is no approve step: `POST /api/runs/<id>/submit` takes a draft straight to the
provider, and calling it is the decision.** Read it before touching anything
that creates or submits a run.

## What studio is

Studio is one service with two halves that share one library.

| Half | Where | Runs | Doc |
|---|---|---|---|
| **The pipeline** — makes the media | `pipeline/` (code) + `.claude/skills/` (docs) | Locally, inside Claude, on the token `studio login` stores. **A thin client** over the API: **no AWS credential, no Replicate credential**; dependencies are `click`, `pyyaml`, `pycognito` and `boto3` for one call — `profiles.aws_session()`, which `studio profile sync` uses to read a stack's outputs. **Never deploys.** | [docs/PIPELINE.md](docs/PIPELINE.md) |
| **The app** — browses the media; plans and submits runs | `backend/`, `frontend/` | `studio.andreas.services` + `studio-api.andreas.services`, deployed by CI as **two images**: the API's, and a render worker's that carries `ffmpeg` | [docs/WEB_APP.md](docs/WEB_APP.md) |
| The library both read | `infra/modules/catalog` + `infra/modules/media` | prod: `studio-prod-catalog` + `s3://studio-prod-media-us-east-1/`. Locally: this machine's dev stack. | [infra/README.md](infra/README.md) |

The library is a DynamoDB table with an S3 bucket behind it — nothing lists the
bucket to find out what exists. The pipeline reaches it only through the API:
`adapters/` holds the API client, the sign-in, the entity records and the object
store; nothing under `pipeline/` opens an S3 or DynamoDB client. Seeding a dev
stack is its own project under `scripts/dev_seed/`, the one tool holding one.

That split is unusual for this monorepo, where a service directory is a
deployable unit and nothing else. It is deliberate: the tools that produce the
library sit beside the app that reads it so the rules below are visible to
anyone working on the app. **A change under `pipeline/`, `.claude/skills/` or
`docs/` deploys nothing** — the CI path filters exclude all three. The pipeline
is one package exposing one command: `studio --help` lists every subcommand,
and `scripts/dev-setup.sh` puts it on PATH.

---

## Hard rules

These hold everywhere in this directory, in every skill, and in anything written
back to it. Full statements and reasoning in
[docs/PIPELINE.md](docs/PIPELINE.md#hard-rules).

### 1. NEVER name a PRODUCTION character in the repo

No production character's name appears in this repository — ever. Not in code,
docstrings, `SKILL.md` files, examples, comments, tests, fixtures, commit
messages, branch names, or PR titles and bodies. Characters are **data**: a row
in the catalog whose `name` is the name, and a folder of nodes hanging off it.
The repo describes the machinery that operates on any character; use the
`<name>` / `<project>` placeholders. The entity model keeps this cheap: keys and
root folders are ids, so nothing but one row spells out any character.

**The rule is env-scoped, not absolute.** A **dev subject** lives only in a
per-machine dev stack and in the shared seed fixture, never in production, and
may be named — the fixture's `catalog.json` lands in git and every path in it is
a name, so the absolute form cannot be kept. Two guards: `dev_seed.source()`
refuses a bucket or table whose name contains `prod` before reading anything, so
a fixture is dev-origin by construction; and `DEV_SUBJECTS` in
`scripts/dev_seed/` is a committed frozenset of the dev subjects this repo
publishes, so adding one is a reviewed diff. Full reasoning in
[docs/PIPELINE.md](docs/PIPELINE.md#the-exception-a-dev-subject-may-be-named).

### 2. NOTHING runs unless a person tells it to

Every generation costs money. Before any submit, show the complete `input`
object as two JSON documents — `PROMPT` then `INPUT` — ask, and submit only
when told. `--dry-run` renders exactly this without billing and leaves a draft.
**The submit command is the act** — `studio run` without `--dry-run`, or
`studio runs submit <run>` on a draft — and **there is no separate approve
step** anywhere: not in the CLI, not in the API, not in the app. In the app,
pressing Send submits. (Decision 2026-09-04; the approve routes, the `approved`
status and the recorded approval are gone.)

**A yes is to a payload, not to a plan.** A yes to "shall I shoot?", a
multiple-choice answer, or a payload shown several messages ago is not an
instruction to send the request about to go out. Show it again and wait. Show
it again after **any** edit. **No flag on a command that spends answers this
for a person, and if one appears, that is a bug** — there is no `--yes`, and
the `--relayed` that once recorded a second-hand yes went with the approve
step it belonged to.

**What the code enforces is smaller than the rule, and says so.**
`POST /api/runs/<id>/submit` is the one route that calls Replicate; it takes a
`draft`, refuses anything already sent, and asks nothing else. What shows a
person the payload is the CLI's render and the app's opened run. The rule is
carried by who calls submit — a person, or an agent that person has explicitly
told to send this run — and the CLI and the SPA hold tokens from the same pool,
so nothing about a token is a permission boundary. The rule above is what stops
"an agent can call submit" from being a formality.

### 2b. NEVER put an image into a character without approval

A character's **identity images** are who it IS, and every later render is
checked against them. An image is one when it carries the `default` tag, so
tagging one — or taking the tag off — is a **separate** decision from having
agreed to spend money rendering something. Show the result, wait for a yes, then
promote it: copy it into the character's tree, then tag the copy.

```bash
studio download <project>/latest#1 --dest /tmp/promote
studio upload --folder <name>/reference /tmp/promote/<file>
studio describe <node> --tag default --tag face
```

**The copy is not optional.** Ownership is the tree: a run's output carrying
`default` is a file in the run's folder with a tag on it, not this character's
identity. A run leaves its results where they are and files nothing on its own.
Both rules were broken in one session — a shoot submitted off a menu answer, its
output then written into a character's face group unasked — which is why they
are stated separately here.

### 3. S3 is the only origin

Assets are never uploaded to a model provider. Anything sent to a model must
already be an S3 object and reaches Replicate only as a short-lived presigned
URL. Enforced in code: `domain/runs.py` refuses a URL-shaped binding.

---

## Environments: a dev stack per machine, prod by name

Studio has a **per-machine dev stack**: its own Cognito pool, media bucket,
catalog table and callback endpoint, named `studio-dev-<short12>-*` and keyed to
a persistent UUID in `~/.config/andreas-services/studio/machine-id`.
`dev-setup.sh` and `dev-up.sh` point at it, and `studio <command>` reads and
writes **that** stack under the `dev` profile. A `delete` you run locally is a
delete in your own stack. The scripts below need AWS credentials — the
long-lived IAM key the root [CLAUDE.md](../CLAUDE.md) describes.

```bash
./studio/scripts/dev-aws-setup.sh                    # once per machine: provision the stack
./studio/scripts/dev-user.sh --generate-password     # once per machine: its test account
./studio/scripts/dev-setup.sh                        # the pipeline half — installs uv, syncs the dev profile
./studio/scripts/dev-up.sh                           # the app half — backend :8000, frontend :5173
./studio/scripts/dev-token.sh                        # prove sign-in works; prints a token
./studio/scripts/dev-aws-seed.sh                     # load the fixture
uv run --project studio/scripts/dev_seed dev-seed tree     # what this stack holds
uv run --project studio/scripts/dev_seed dev-seed publish --path <p>   # dry run
./studio/scripts/dev-aws-reset.sh --dry-run          # what a reset would remove
./studio/scripts/dev-aws-destroy.sh                  # tear it down; the machine id is kept
```

`dev-setup.sh` runs from the SessionStart hook, tolerates a missing stack, and
writes `frontend/.env.local` and the `dev` profile from the stack's Terraform
outputs — re-run it, or `studio profile sync dev`, rather than editing either.
It names a stale pin in `studio/.env` rather than rewriting it; delete the line.
`dev-up.sh` refuses to start without a stack: an API with no Cognito pool 500s.

**The stack is seeded — not empty, and not a copy of prod.** `dev-aws-seed.sh`
loads a published fixture: `v1` holds one character and its seed pool, 54
stills, copied server-side in about two seconds. `dev-setup.sh` adds the shared
material with `studio config sync` — the angle images, nothing else. No runs,
scenes or movies, because those are model output and cost money. Publishing is
human-gated but generates nothing: `dev-seed publish` promotes nodes that
already exist, calls no model and costs nothing. The gate is hard rule #1 —
`catalog.json` lands in git, so the publisher requires `--dev-subjects-only`
before `--apply` and refuses any name outside `DEV_SUBJECTS`. `infra/README.md`
has the selection rules.

**The dev stack's callback endpoint is the only public one studio has.**
`module.callbacks` gives each machine an API Gateway, an SQS queue and a small
receiver Lambda — a zip built from `backend/`, no ECR — because Replicate cannot
call back to `http://localhost:8000`. `dev-up.sh` runs a consumer that drains
the queue and closes the run **with the working tree**. A stack without the
endpoint still works: a finished generation waits for `studio runs reconcile
<run>`; re-apply with `dev-aws-setup.sh`. `dev-aws-destroy.sh` takes the queue
with it, so a callback in flight during a teardown is lost.

**`STUDIO_DEV_MACHINE_ID` targets a stack this machine did not create** — an
ephemeral environment whose generated id would die with the container and leave
the stack running and billing, or a second machine reaching an existing stack
deliberately. `dev-aws-common.sh` persists it. The machine id is the only
handle on the resources; losing it strands a running, billing stack.

### Reaching production: `--profile prod`

```bash
studio --profile prod runs list        # one invocation
STUDIO_PROFILE=prod studio runs list   # the same thing, written the other way
studio profile list                    # what exists, and which is in force
studio profile show                    # what each value resolves to, and from where
```

A profile carries all five values that decide which stack answers — the API URL,
both Cognito ids, the media bucket and the catalog table — in
`~/.config/andreas-services/studio/config`, beside the machine id and the
`<profile>.env` account files. Nothing in it is secret.

- **`dev` is the default, and there is no other default.** Nothing configured is
  a refusal, never a fallback to production.
- **An explicit `--profile` beats an exported `STUDIO_API_URL`**, and says so on
  stderr. `dev-up.sh` exports those variables, and if one of them won,
  `--profile prod` typed in that window would silently keep talking to dev —
  the opposite of the AWS CLI's rule, which `scripts/dev-aws-common.sh`
  documents as a footgun.
- **Sessions are per-profile.** Signing in to prod does not sign you out of dev.
- **Selecting `prod` is sufficient intent — there is no confirmation step.**
  Hard rule #2 still applies wherever a generation runs.
- **A profile decides whose Replicate account pays, indirectly.** The CLI holds
  no provider token; the API it points at does — the deployed API's under
  `--profile prod`, `~/.config/andreas-services/studio/dev.env` in a `dev-up.sh`
  shell. Both are real money.
- **A profile is not a permission boundary.** The only tool holding an AWS client
  is `dev-seed`, which runs under your own IAM key and defaults to `dev`.

**The prod bucket's protections matter.** Versioning is on, and neither the API
role nor your own commands are granted `s3:DeleteObjectVersion`, so every delete
there is a recoverable tombstone. Do not "tidy up" that grant. Reading prod
without any of this is the lightest option: `studio.andreas.services` shows the
same library.

---

## Which skill

**Load one before doing anything else in `studio/`.** Nineteen skills in **two
families** — eighteen `studio-media-*` and one `studio-code-*`; route by what
the task *changes*, not by what it mentions.

| If the task changes… | Load | Examples |
|---|---|---|
| **media, or a catalog record** — an image, a clip, a character, a project, a run | a **`studio-media-*`** skill | "make a shot of…", "add a reference", "what characters do we have", "cut these scenes together" |
| **studio's own code** — anything under `pipeline/`, `backend/`, `frontend/`, `infra/` | **`studio-code-pipeline`** | "add a subcommand", "fix this import", "why does this test fail", "move this module" |

The families differ in what they may say: a `studio-media-*` skill describes
the **CLI surface** and never names a module; `studio-code-*` names modules
because the code is its subject. Enforced by `pipeline/scripts/lint_skills.py`,
which also rejects any skill outside the two families.

**Load the skill with the Skill tool. Do not skim its `SKILL.md`.** These pages
put the concepts up top and the runnable commands further down, so reading the
first screen and starting work reliably ends in raw `aws s3` calls rebuilding
what a `studio` subcommand already returns. `studio --help` lists the whole
command surface and is the fastest correction when unsure a command exists.
The app half (`backend/`, `frontend/`) has no skill of its own; read
[docs/WEB_APP.md](docs/WEB_APP.md) directly.

### The `studio-media-*` skills

| You want to | Use |
|---|---|
| Store, fetch, list or presign anything; record a run | `studio-media-s3` |
| Make a still image | `studio-media-image`, then a model skill |
| Enlarge or restore an image that already exists | `studio-media-image-upscale` |
| Make one shot end to end (still → motion) | `studio-media-shot` |
| Continue past a model's duration ceiling | `studio-media-scene` |
| Cut finished scenes into one piece | `studio-media-movie` |
| Work with a recurring character | `studio-media-character` |
| Write a tight, repeatable video prompt | `studio-media-prompt` |
| Invoke a model generically, or inspect its schema | `studio-media-core` |
| Register a new Replicate model | `studio-media-add-model` |
| Pick a video engine | `studio-media-seedance` · `studio-media-kling` · `studio-media-veo-3-1` · `studio-media-grok-imagine-video` |
| Pick an image engine | `studio-media-nano-banana-pro` · `studio-media-nano-banana-2` · `studio-media-gpt-image-2` · `studio-media-gpt-image-1-5` |

**Ask which project before generating anything.** A run belongs to a project;
guessing puts runs somewhere nobody looks again. `--project` takes a project id,
or a name matched over the listing — an ambiguous name is refused with the ids.

---

## Conventions that bite

- **`SKILL.md` files are documentation; the code is in `pipeline/`.** Adding a
  command means a module under `pipeline/src/studio_pipeline/`, an entry in
  `cli.py`, then a description in the relevant `SKILL.md`.
- **A `studio-media-*` skill never names a module, path or function; a
  `studio-code-*` skill may.** Internals are documented once, in
  [docs/PIPELINE.md](docs/PIPELINE.md#the-modules), beside the code.
  `pipeline/scripts/lint_skills.py` fails on a module name in a media skill, a
  module a code skill names that does not exist, a `studio …` line naming no
  real command, a surviving script-era invocation, and a broken link, and runs
  the command, path, link and `/api/...` route checks over this directory's
  docs too. A **linter, not a test** — pre-commit runs it, `studio-pr.yml`
  enforces it.
- **No code in this repo generates prose.** `studio add-model` writes the
  registry entry and stops; `studio-media-add-model` writes the model's page.
- **One constant knows where `studio/` is**: `studio_pipeline.STUDIO_DIR`.
- **Claude Code does not read a nested `settings.json`.** New Bash permissions
  for these skills go in the **monorepo root** `.claude/settings.json`.
- **One package, one dependency set** (`pipeline/pyproject.toml`, `uv.lock`).
  The backend builds with Poetry (`backend/pyproject.toml`, `backend/poetry.lock`).
- **`--help` is not a test.** Usage prints happily while a module references an
  undefined name or a group has no handler. `pipeline/tests/` covers wiring and
  *execution*, and runs on PR even though the pipeline deploys nowhere.
- **The prod deploy ends in a smoke run against the live API — a detector, not
  a gate.** Studio has no staging, so it runs *after* the new image is serving,
  and it is the only thing that exercises the Lambda's own execution role. It
  signs in as an account that is a member of **exactly one library**;
  `seeds/smoke.json`, `scripts/prod-seed-smoke.py` and `backend/tests/smoke/`
  hold that up. It finds the library root through `GET /api/resolve`, which is
  why that route stays although the SPA does not call it. See
  [docs/PROD_SMOKE.md](docs/PROD_SMOKE.md).
- **The CLI surface is a contract.** `pipeline/tests/contracts/cli_surface_reference.json`
  records every option, arity, default and help string. Changing the CLI means
  regenerating it deliberately — never editing it to make a test pass.
- **`terraform destroy` on `studio/prod` fails by design.** The media bucket
  carries `prevent_destroy`; see [infra/README.md](infra/README.md).
- **Moving an object does not rewrite the records that name it.** A record
  names a **node id**, so every pointer stays correct. A blob's
  `<owner_kind>/<owner_id>/` key prefix can drift after a move; it is a pointer
  `services/catalog.py` keeps opaque, and the drift is cosmetic.
- The app's API takes the **ID token**, not the access token; the run JSON is
  deliberately served as text and never parsed. More in
  [docs/WEB_APP.md](docs/WEB_APP.md#conventions--gotchas).

## Testing

**Five tiers, decided by what a test is allowed to touch** — conftest
inheritance is scoped by directory, so the tier boundary is the guard boundary.

| Tier | Runs | Talks to | Gate |
|---|---|---|---|
| `pipeline/tests/unit/` | every PR | the in-memory `fake_api` | — |
| `pipeline/tests/contracts/` | every PR | nothing; named for the FAILURE they catch | — |
| `backend/tests/unit/` | every PR | moto + the Flask test client | — |
| `frontend` vitest + `e2e/` | every PR | jsdom; e2e stubs `/api/**` from captured fixtures | — |
| `*/tests/integration/` | **never in CI** | real S3, DynamoDB, Cognito, the running API | `STUDIO_INTEGRATION=1` |

```bash
uv run --project studio/pipeline pytest studio/pipeline/tests -q   # + backend, frontend
cd studio/frontend && npm test && npm run e2e                      # vitest, then Playwright
studio/scripts/dev-test-integration.sh          # both integration suites; needs dev-up.sh
```

What a new test may not do — each enforced; a guard in the way means the test
belongs in a different tier:

- **Do not stub the model provider yourself.** In `backend/`,
  `STUDIO_REPLICATE_MODE=fake` is autouse and `clients/replicate.py` answers
  every call locally. In `pipeline/` submitting is `POST /api/runs/<id>/submit`,
  `tests/support/fake_api.py` answers it, and the seam is
  `fake_api.submits_refused`.
- **Do not reach the network.** A socket guard allows loopback only in the unit
  suites, and blocks the provider hosts in the integration suites.
- **Do not write to the repo.** The registry path is redirected at a per-test
  copy: `studio models refresh` rewrites `backend/studio_core/models.json`.
- **Do not edit `cli_surface_reference.json` to make a test pass.** Regenerate it
  with `tests.contracts.update_cli_reference <command>`.
- **Do not capture an API fixture with `curl`.** `GET /api/nodes` answers with
  presigned URLs; `frontend/e2e/fixtures/capture.py` scrubs them.
- **Do not skip a tree at module level.** An unfiltered
  `pytest_collection_modifyitems` hook or `test.skip(...)` skips everything and
  exits 0.

**Coverage is measured and gates on nothing.** `pytest-cov` on both Python
suites, `@vitest/coverage-v8` on the frontend, report-only in `studio-pr.yml`;
there is deliberately no `--cov-fail-under`. Each suite's `tests/__init__.py`
is its map; `studio-code-pipeline` covers the pipeline's,
`frontend/e2e/README.md` the browser one.
