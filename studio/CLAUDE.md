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
| The library both read | `infra/modules/catalog` + `infra/modules/media` | prod: `studio-prod-catalog` + `s3://studio-prod-media-us-east-1/`. Locally: this machine's dev stack. | [infra/README.md](infra/README.md) |

**That row used to name the prod bucket flatly, and it is now two corrections
deep.** The library is a DynamoDB table with an S3 bucket behind it — nothing
lists the bucket to find out what exists — and the pipeline half runs against
this machine's `studio-dev-<short12>-*` stack, not against prod.

That split is unusual for this monorepo, where a service directory is normally a
deployable unit and nothing else. It is deliberate: the tools that produce the
library and the app that reads it were separate repos until August 2026, and
keeping them apart meant the rules below were invisible to anyone working on the
app. **A change under `pipeline/`, `.claude/skills/` or `docs/` deploys
nothing** — the CI path filters exclude all three.

The pipeline is one package exposing one command. `studio --help` lists every
subcommand; `scripts/dev-setup.sh` installs it and puts it on PATH.

The bucket was named from that era and did not follow the repo's
`[project]-[env]-[component]-[region]` convention. It was renamed in August
2026 — a second bucket plus a verified copy, because S3 has no rename and the
old one held the only copy of the media. The original,
`xharness-prod-media-us-east-1`, was then deleted, which destroyed the version
history the copy did not carry. See [infra/README.md](infra/README.md).

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

**Approval is of a payload, not of a plan.** A yes to "shall I shoot?", a
multiple-choice answer, or a payload shown several messages ago is not approval
of the request about to be sent. Show it again and wait. No flag exists to
answer this for a person, and if one appears, that is a bug.

### 2b. NEVER put an image into a character without approval

`characters/<name>/reference/` is who the character IS, and every later render is
checked against it. Adding, replacing, renumbering or archiving anything there —
or in `default_set` or the bible's `references:` index — is a **separate**
decision from having agreed to spend money rendering something. Show the result,
wait for a yes, then promote it:

```bash
studio character add-refs <name> --to <group> --from-run <runref>
```

`studio character shoot` therefore leaves its results in their runs and files
nothing on its own. Both of these rules were broken in one session — a shoot
submitted off a menu answer, its output then written into a character's face
group unasked — which is why they are stated separately here.

### 3. S3 is the only origin

Assets are never uploaded to a model provider. Anything sent to a model must
already be an S3 object and reaches Replicate only as a short-lived presigned
URL. This is enforced in code: `runs.py` refuses a URL-shaped binding.

---

## LOCAL RUNS AGAINST A DEV STACK. THIS CHANGED IN AUGUST 2026.

**This section used to be headed "LOCAL RUNS AGAINST PROD. THIS IS
DELIBERATE."** It is kept, inverted, rather than deleted, because anyone who
learned studio before now learned the opposite rule and needs to find out what
replaced it.

Studio has a **per-machine dev stack**: its own Cognito pool, media bucket and
catalog table, named `studio-dev-<short12>-*` and keyed to a persistent UUID in
`~/.config/andreas-services/studio/machine-id`. `dev-setup.sh` and `dev-up.sh`
point at it. `studio <command>` reads and writes **that** bucket.

### What the old rule said, and why it was not simply wrong

It said a second, empty bucket would exercise none of the behaviour that
matters — the listing, the sorting, the reel, the tidy-up all only mean anything
against real material — and that keeping two copies of ~700 MB in sync would be
its own failure mode.

**Both points were correct. The answer is that the dev stack is not meant to be
empty and is not a copy.** It is seeded from a small, purpose-made fixture
published once and downloaded per machine (#284, #285): real model output,
chosen to exercise the shapes the app cares about, and never a copy of anyone's
production library.

**That is the design, and half of it is not built.** The loader is
`dev-aws-seed.sh` (#285); the fixture is #284, needs a human to generate it, and
does not exist. So a stack today is empty apart from the shared material, and
the paragraph above describes where this is going rather than what you will
find.

### What follows from the change

- **A `delete` you run locally is no longer a delete in production.** The old
  section's warnings about that are retired. What you can now destroy is your own
  dev stack, and `dev-aws-destroy.sh` exists to do it deliberately.
- **The prod bucket's protections are unchanged and still matter.** Versioning is
  on, and neither the API role nor your own commands are granted
  `s3:DeleteObjectVersion`, so every delete there is a recoverable tombstone. Do
  not "tidy up" that grant. It guards the deployed service, which is still real.
- **`dev-setup.sh` writes `frontend/.env.local` and pins `STUDIO_S3_BUCKET` and
  `STUDIO_CATALOG_TABLE` in `.env` from the dev stack's Terraform outputs** — not
  from SSM, which holds what the deploy workflow wrote and knows nothing about a
  dev stack. Re-run it rather than editing either file.
- **A `.env` pinned to a prod bucket predates this change.** `dev-setup.sh` names
  it loudly rather than rewriting it — the file is yours — but it points your
  commands at production and should be changed.

### The one thing that is genuinely unsettled

**Running the CLI against production is still wanted sometimes, and how to do it
safely is undecided.** There is no flag, no environment variable and no
documented procedure, and that is not an oversight — it is an open question.

Do not design one unprompted, and do not reintroduce the old behaviour as a
convenience. If you need prod data in front of you today, the deployed app at
`studio.andreas.services` reads it.

### Provisioning one

```bash
./studio/scripts/dev-aws-setup.sh                    # provision this machine's stack
./studio/scripts/dev-user.sh --generate-password     # its one test account
./studio/scripts/dev-token.sh                        # prove sign-in works; prints a token
./studio/scripts/dev-aws-seed.sh                     # load the fixture — see below
./studio/scripts/dev-aws-reset.sh --dry-run          # what a reset would remove
./studio/scripts/dev-aws-destroy.sh                  # tear it down; the machine id is kept
```

**`dev-aws-seed.sh` has never loaded anything.** The fixture it downloads is
#284, which is human-gated because it generates media, and the bucket it would
live in does not exist — so the script stops on its first read and says so. What
a fresh stack actually holds is the shared material `dev-setup.sh` pushes: the
pose plates, and a starting `phrasebook/wording.yaml` (#425).

**`STUDIO_DEV_MACHINE_ID` targets a stack this machine did not create.** Export
it and every command above agrees, because `dev-aws-common.sh` persists it. Two
cases need it: an ephemeral environment, where a generated id dies with the
container and leaves the stack running, billing and unreachable; and a second
machine reaching an existing stack deliberately.

The machine id is the only handle on the resources — the Terraform state key is
built from it. Losing it strands a running, billing stack.

---

## Which skill

**Load one before doing anything else in `studio/`.** Sixteen skills in **two
families**; route by what the task *changes*, not by what it mentions.

| If the task changes… | Load | Examples |
|---|---|---|
| **media, or an S3 record** — an image, a clip, a character, a project, a run | a **`studio-media-*`** skill | "make a shot of…", "add a reference", "what characters do we have", "cut these scenes together" |
| **studio's own code** — anything under `pipeline/`, `backend/`, `frontend/`, `infra/` | **`studio-code-pipeline`** | "add a subcommand", "fix this import", "why does this test fail", "move this module" |

The families differ in what they are allowed to say, which is why the split
exists: a `studio-media-*` skill describes the **CLI surface** and never names a
module; `studio-code-*` names modules because the code is its subject. Enforced
by `pipeline/scripts/lint_skills.py`.

**Load the skill with the Skill tool. Do not skim its `SKILL.md`.** These pages
put the S3 layout and the concepts up top and the runnable commands further
down, so reading the first screen and starting work reliably produces the wrong
approach — most often falling back to raw `aws s3` calls to rebuild by hand what
a `studio` subcommand already returns. If you have read half a page and are
reaching for the AWS CLI, that is the signal you skipped the skill.

`studio --help` lists the whole command surface and is the fastest correction
when you are unsure a command exists.

> The app half (`backend/`, `frontend/`) has no skill of its own yet.
> `studio-code-pipeline` covers the pipeline; for the deployed service read
> [docs/WEB_APP.md](docs/WEB_APP.md) directly. A second `studio-code-*` skill
> can be added when one earns its place — the linter rejects any skill outside
> the two families, so the prefix is not optional.

### The `studio-media-*` skills

| You want to | Use |
|---|---|
| Store, fetch, list or presign anything; record a run | `studio-media-s3` |
| Make a still image | `studio-media-image`, then a model skill |
| Make one shot end to end (still → motion) | `studio-media-shot` |
| Continue past a model's duration ceiling | `studio-media-scene` |
| Cut finished scenes into one piece | `studio-media-movie` |
| Work with a recurring character | `studio-media-character` |
| Write a tight, repeatable video prompt | `studio-media-prompt` |
| Invoke a model generically, or inspect its schema | `studio-media-core` |
| Register a new Replicate model | `studio-media-add-model` |
| Pick a video engine | `studio-media-seedance` · `studio-media-kling` |
| Pick an image engine | `studio-media-nano-banana-pro` · `studio-media-nano-banana-2` · `studio-media-gpt-image-2` · `studio-media-gpt-image-1-5` |

**Ask which project before generating anything.** Work is addressed as
`projects/<project>/`, and guessing puts runs somewhere nobody looks again.

---

## Conventions that bite

- **`SKILL.md` files are documentation; the code is in `pipeline/`.** A skill
  directory holds prose and nothing else. Adding a command means adding a module
  under `pipeline/src/studio_pipeline/` and an entry in `cli.py`, then
  describing it in the relevant `SKILL.md`.
- **A `studio-media-*` skill describes the CLI surface and never names a module,
  path or function; a `studio-code-*` skill may, because the code is its
  subject.** Internals are documented once, in
  [docs/PIPELINE.md](docs/PIPELINE.md#the-modules), next to the code they
  describe. Two media skills used to carry module tables and five of those names
  rotted into files that no longer existed — prose about code only stays true
  when it lives beside the code. `pipeline/scripts/lint_skills.py` enforces this:
  it fails on a module name in a media skill, on a module a code skill names that
  does not exist, on a `studio …` line naming no real command, on a surviving
  script-era invocation, and on a broken link. It is a **linter, not a test** —
  pre-commit runs it locally, `studio-pr.yml` enforces it.
- **No code in this repo generates prose.** `studio add-model` writes the
  registry entry and stops; `studio-media-add-model` writes the model's page. The
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

**A dev stack comes first.** Both scripts below read this machine's, and
`dev-up.sh` refuses to start without one — an API with no Cognito pool 500s on
every call, so failing early is the faster way to find out.

```bash
studio/scripts/dev-aws-setup.sh                    # once per machine: provision the stack
studio/scripts/dev-user.sh --generate-password     # once per machine: its test account
studio/scripts/dev-setup.sh                        # the pipeline half — installs uv, warms caches
studio/scripts/dev-up.sh                           # the app half — backend :8000, frontend :5173
```

`dev-setup.sh` runs from the SessionStart hook and **tolerates a missing stack**,
warning and carrying on; it still has a toolchain to install. `dev-up.sh` does
not.

All three need a live AWS login (`aws login`). Note the credential split the root
[CLAUDE.md](../CLAUDE.md) documents: the AWS CLI reads its own login cache,
boto3 and the Terraform provider do not, so export before running Terraform:

```bash
eval "$(aws configure export-credentials --format env)"
```
