# Claude Instructions – studio

**Read the hard rules below before doing anything else in this directory.** They
are not preferences, and two of them are about spending money and leaking
identity. Everything else in this file is an index.

**The data model is [docs/ENTITY_MODEL.md](docs/ENTITY_MODEL.md)**, worked
through one character and one project in
[docs/ENTITY_MODEL_EXAMPLE.md](docs/ENTITY_MODEL_EXAMPLE.md). Characters,
projects, runs, scenes and movies are rows with UUIDs; the folder tree hangs off
them; S3 keys carry ids and never names. Read it before assuming a slug is a
path or that a document defines anything.

**A run now has an authored half too — [docs/RUN_PLAN.md](docs/RUN_PLAN.md).** It
is created as a `draft` when it is PLANNED rather than when it is submitted, so
the row no longer asserts that anything happened; it carries a `plan`, one
`SEND#` row per bound image, and an `approval` bound to a hash of both. **The API
refuses to move a run out of the unsubmitted states unless it is approved and
that hash still matches**, which is hard rule #2 made mechanical rather than
remembered. Read it before touching anything that creates or submits a run.

## What studio is

Studio is one service with two halves that share one library.

| Half | Where | Runs | Doc |
|---|---|---|---|
| **The pipeline** — makes the media | `pipeline/` (code) + `.claude/skills/` (docs) | Locally, inside Claude, on the token `studio login` stores — **no AWS credentials at all** (#308). **Never deploys.** | [docs/PIPELINE.md](docs/PIPELINE.md) |
| **The app** — browses the media | `backend/`, `frontend/` | `studio.andreas.services` + `studio-api.andreas.services`, deployed by CI | [docs/WEB_APP.md](docs/WEB_APP.md) |
| The library both read | `infra/modules/catalog` + `infra/modules/media` | prod: `studio-prod-catalog` + `s3://studio-prod-media-us-east-1/`. Locally: this machine's dev stack. | [infra/README.md](infra/README.md) |

**That row used to name the prod bucket flatly, and it is now three corrections
deep.** The library is a DynamoDB table with an S3 bucket behind it — nothing
lists the bucket to find out what exists; the pipeline half runs against this
machine's `studio-dev-<short12>-*` stack, not against prod; and it reaches it
through the API rather than through an AWS login of its own. Only the six
`maintenance/` one-shots and `adapters/ddb.py` still open AWS clients of
their own.

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

### 1. NEVER name a PRODUCTION character in the repo

No production character's name appears in this repository — ever. Not in code,
docstrings, `SKILL.md` files, examples, comments, tests, fixtures, commit
messages, branch names, or PR titles and bodies. Characters are **data**: a row
in the catalog whose `slug` is the name, and a folder of nodes hanging off it.
The repo describes the machinery that operates on any character; use the
`<name>` / `<project>` / `<slug>` placeholders.

The entity model made this cheaper to keep. A slug is an attribute rather than
a path segment and an S3 key is built from ids, so a bucket listing no longer
spells out every character in the library — which it did, for as long as the
key was `characters/<name>/…`.

**This rule used to be absolute — "never name a character anywhere" — and it was
narrowed in August 2026 rather than dropped.** A **dev subject** lives only in a
per-machine dev stack and in the shared seed fixture, never in production, and
may be named: the fixture's `catalog.json` lands in git and every path in it is
a name, so the absolute form made #284 impossible to finish. Two guards, of
different kinds:

- **Mechanical** — `dev_seed.source()` refuses a bucket or table whose name
  contains `prod` before reading anything, so a fixture is dev-origin by
  construction.
- **Deliberate** — `DEV_SUBJECTS` in `maintenance/dev_seed.py` is a committed
  frozenset of the dev subjects this repo publishes. Adding one is a reviewed
  diff, which is where "should this likeness be in a fixture every machine
  downloads" gets asked.

It replaced two regexes that matched on the *shape* of a name and could not tell
`mira` from `demo`. Full reasoning in
[docs/PIPELINE.md](docs/PIPELINE.md#the-exception-a-dev-subject-may-be-named).

### 2. NEVER submit without approval of the FULL payload

Every generation costs money. Before any submit, show the complete `input`
object as two JSON documents — `PROMPT` then `INPUT` — and get explicit
approval. Re-approve after **any** edit. `--dry-run` renders exactly this
without billing.

**Approval is of a payload, not of a plan.** A yes to "shall I shoot?", a
multiple-choice answer, or a payload shown several messages ago is not approval
of the request about to be sent. Show it again and wait. **No flag on a command
that spends answers this for a person, and if one appears, that is a bug.**

`runs approve --relayed` is the one adjacent thing that exists, and it is not an
exception: it records a yes given elsewhere, spends nothing, prints the payload
anyway, and stamps the row `via: relayed` so it reads as the weaker claim it is.
It was added because forbidding it never worked — `yes |` cleared the confirm —
and the row it produced was indistinguishable from a person clicking the
button.

**Half of this is now enforced rather than remembered.** A run is created as a
draft, an approval records the digest of the payload it was given for, and the
API refuses the submission if the plan or the images have moved since — so
approve-then-edit is a 409 rather than something nobody notices. It is **not** a
permission boundary: the CLI and the SPA hold tokens from the same pool, so an
agent can approve a run it wrote. The rule above is what stops that being a
formality; the mechanism only stops the yes drifting from what it was for. See
[docs/RUN_PLAN.md](docs/RUN_PLAN.md).

### 2b. NEVER put an image into a character without approval

A character's **references** are who it IS, and every later render is checked
against them. A reference is a `REF#` row naming a node, so adding, describing,
regrouping or detaching one — or changing `default_set` — is a **separate**
decision from having agreed to spend money rendering something. Show the result,
wait for a yes, then promote it:

```bash
studio character add-refs <name> --to <group> --from-run <runref>
```

`studio character turnaround` therefore leaves its results in their runs and files
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

**That is the design, and the last step of it has not been taken.** The loader
is `dev-aws-seed.sh` (#285); the seed bucket and the writer are #284 —
`infra/modules/dev_seed`, wired into `envs/prod` and applied by CI, and `studio
dev-seed publish`. Both landed; **`publish` has never been run.** So no fixture
exists, a stack today is still empty apart from the shared material, and the
paragraph above describes where this is going rather than what you will find.
(This used to add that the bucket had never been applied. Do not assert that
either way from here — see [infra/README.md](infra/README.md).)

What is left is not code. `publish` **promotes** a fixture out of a dev stack
rather than generating one — it calls no model and costs nothing — so someone
has to drive their own stack through a session first, with placeholder names
from the first generation, and then choose the six to eight nodes worth every
machine downloading. `infra/README.md` has the selection rules and the
hard-rule-#1 guard.

### What follows from the change

- **A `delete` you run locally is no longer a delete in production.** The old
  section's warnings about that are retired. What you can now destroy is your own
  dev stack, and `dev-aws-destroy.sh` exists to do it deliberately.
- **The prod bucket's protections are unchanged and still matter.** Versioning is
  on, and neither the API role nor your own commands are granted
  `s3:DeleteObjectVersion`, so every delete there is a recoverable tombstone. Do
  not "tidy up" that grant. It guards the deployed service, which is still real.
- **`dev-setup.sh` writes `frontend/.env.local` and syncs the `dev` profile** from
  the dev stack's Terraform outputs — not from SSM, which holds what the deploy
  workflow wrote and knows nothing about a dev stack. Re-run it, or run
  `studio profile sync dev`, rather than editing either by hand.
- **It used to pin `STUDIO_S3_BUCKET` and `STUDIO_CATALOG_TABLE` into `.env`
  instead, and no longer does.** A pin was per-checkout while the stack is
  per-machine, and it covered two of the five values that select a stack — so a
  second worktree had none of them, and a `.env` and a `dev-up.sh` shell could
  name different environments with nothing printing either. The profile carries
  all five.
- **A `.env` pinned to a prod bucket predates this change and still wins whenever
  no profile is selected.** `dev-setup.sh` names it loudly rather than rewriting
  it — the file is yours — but it points your commands at production. Delete the
  line; `studio profile show` says what answers instead.

### Reaching production: `--profile prod`

**This section used to say the mechanism was undecided. It is decided.** The CLI
has named environments, modelled on the AWS CLI's:

```bash
studio --profile prod runs list        # one invocation
STUDIO_PROFILE=prod studio runs list   # the same thing, written the other way
studio profile list                    # what exists, and which is in force
studio profile show                    # what each value resolves to, and from where
```

A profile carries all five values that decide which stack answers — the API URL,
both Cognito ids, the media bucket and the catalog table. They live in
`~/.config/andreas-services/studio/config`, beside the machine id and the two
`<profile>.env` account files that already used that naming. Nothing in it is
secret: passwords stay in `<profile>.env`, and `REPLICATE_API_TOKEN` is not a
profile field because it is not environment-scoped.

Four things worth knowing before using it:

- **`dev` is the default, and there is no other default.** `auth.py` used to fall
  back to `https://studio-api.andreas.services`, so a shell with nothing set
  talked to production. That is deleted; nothing configured is now a refusal.
- **An explicit `--profile` beats an exported `STUDIO_API_URL`**, and prints on
  stderr that it is doing so. It has to be that way round: `dev-up.sh` exports
  those variables, and if one of them won, `--profile prod` typed in that window
  would silently keep talking to dev. This is the opposite of the AWS CLI, whose
  version of the rule `scripts/dev-aws-common.sh` documents as a footgun.
- **Sessions are per-profile.** Signing in to prod no longer signs you out of
  dev; a pre-profile `credentials` file is filed under the profile whose pool
  minted its token.
- **Selecting `prod` is treated as sufficient intent — there is no confirmation
  step.** Hard rule #2 is untouched and still applies: a generation shows its
  full payload and waits for a yes wherever it runs.

**A profile is not a permission boundary.** `catalog gc`, `catalog verify` and
`dev-seed` reach S3 and DynamoDB under your own IAM key, which holds
`s3:DeleteObjectVersion` — a grant the deployed API's role deliberately lacks, and
the thing that makes every delete through the app a recoverable tombstone.
`--profile prod` does not narrow that, so `catalog gc --apply` against prod is
the one path with no safety net. Least-privilege credentials for prod
maintenance are a separate, unstarted piece of work.

Reading prod without any of this still works, and is still the lightest option:
the deployed app at `studio.andreas.services` shows the same library.

### Provisioning one

```bash
./studio/scripts/dev-aws-setup.sh                    # provision this machine's stack
./studio/scripts/dev-user.sh --generate-password     # its one test account
studio profile sync dev                              # point the CLI at it (dev-setup.sh does this)
./studio/scripts/dev-token.sh                        # prove sign-in works; prints a token
./studio/scripts/dev-aws-seed.sh                     # load the fixture — see below
studio dev-seed tree                                 # what this stack holds, by path
studio dev-seed publish --path <p>                   # promote a fixture (dry run)
./studio/scripts/dev-aws-reset.sh --dry-run          # what a reset would remove
./studio/scripts/dev-aws-destroy.sh                  # tear it down; the machine id is kept
```

**A fixture exists, and `dev-aws-seed.sh` loads it.** `v1` was published on
2026-08-27 — the first publish since #284 landed — and holds one character and
its seed pool: 54 stills, 12.4 MB, loaded in about two seconds by `studio
dev-seed load` — the bytes are copied server-side and never come through this
machine. Everything above this paragraph used to say the opposite. Publishing is
human-gated, but **not because it generates media**: `studio dev-seed publish`
promotes nodes that already exist, calls no model and costs nothing.
The gate is hard rule #1 — `catalog.json` lands in git, so the publisher refuses
a stack holding any name outside `DEV_SUBJECTS` and requires
`--dev-subjects-only` before `--apply`. What a fresh stack actually holds is the
shared material `dev-setup.sh` pushes: the angle images, and nothing else. It
used to seed a starting `phrasebook/wording.yaml` too (#425); the phrasebook is
`TERM#` rows now, so there is no document to seed.

**`STUDIO_DEV_MACHINE_ID` targets a stack this machine did not create.** Export
it and every command above agrees, because `dev-aws-common.sh` persists it. Two
cases need it: an ephemeral environment, where a generated id dies with the
container and leaves the stack running, billing and unreachable; and a second
machine reaching an existing stack deliberately.

The machine id is the only handle on the resources — the Terraform state key is
built from it. Losing it strands a running, billing stack.

---

## Which skill

**Load one before doing anything else in `studio/`.** Eighteen skills in **two
families** — seventeen `studio-media-*` and one `studio-code-*`; route by what
the task *changes*, not by what it mentions.

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
| Pick a video engine | `studio-media-seedance` · `studio-media-kling` · `studio-media-veo-3-1` · `studio-media-grok-imagine-video` |
| Pick an image engine | `studio-media-nano-banana-pro` · `studio-media-nano-banana-2` · `studio-media-gpt-image-2` · `studio-media-gpt-image-1-5` |

**Ask which project before generating anything.** A run belongs to a project and
records which characters it used; guessing puts runs somewhere nobody looks
again. `--project` takes a slug or a project id and is never inferred.

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
- **The prod deploy ends in a smoke run against the live API, and it is a
  detector rather than a gate.** Studio has no staging, so it runs *after* the
  new image is already serving. It is the only thing that exercises the Lambda's
  own execution role — moto enforces no IAM and the integration suite runs under
  a developer's far wider credentials — which is how a missing
  `dynamodb:BatchGetItem` grant reached production. It signs in as an account
  that is a member of **exactly one library** and can address nothing else; that
  is the mechanism, not a courtesy, and `seeds/smoke.json`,
  `scripts/prod-seed-smoke.py` and `backend/tests/smoke/` all hold it up. See
  [docs/PROD_SMOKE.md](docs/PROD_SMOKE.md).
- **The CLI surface is a contract.** `pipeline/tests/contracts/cli_surface_reference.json`
  records every option, arity, default and help string. Changing the CLI means
  regenerating it deliberately — never editing it to make a test pass.
- **`terraform destroy` on `studio/prod` fails by design.** The media bucket
  carries `prevent_destroy`; see [infra/README.md](infra/README.md).
- **Moving an object no longer means rewriting the records that name it.**
  Skipping that step is what once left 69 records pointing at reference images
  that no longer existed, and `domain/rewrite.py` existed to patch them. Both
  the hazard and the tool are gone: a record names a **node id**, so a move
  changes a node's parent and every record pointing at it stays correct. What
  can still drift is a blob's `<owner_kind>/<owner_id>/` key prefix, which is a
  pointer rather than a name — `verify` reports it and `studio catalog reseat`
  rewrites it, out of band and never automatically.
- The app's API takes the **ID token**, not the access token; the run JSON is
  deliberately served as text and never parsed. More in
  [docs/WEB_APP.md](docs/WEB_APP.md#conventions--gotchas).

## Testing

**Five tiers. Which one a test belongs in is decided by what it is allowed to
touch, and that is the same question as which guards apply to it** — conftest
inheritance is scoped by directory, so the tier boundary and the guard boundary
are one line.

| Tier | Runs | Talks to | Gate |
|---|---|---|---|
| `pipeline/tests/unit/` | every PR | moto + the in-memory `fake_api` | — |
| `pipeline/tests/contracts/` | every PR | nothing; named for the FAILURE they catch | — |
| `backend/tests/unit/` | every PR | moto + the Flask test client | — |
| `frontend` vitest + `e2e/` | every PR | jsdom; e2e stubs `/api/**` from captured fixtures | — |
| `*/tests/integration/` | **never in CI** | real S3, DynamoDB, Cognito, the running API | `STUDIO_INTEGRATION=1` |

```bash
uv run --project studio/pipeline pytest studio/pipeline/tests -q   # + backend, frontend
cd studio/frontend && npm test && npm run e2e                      # vitest, then Playwright
studio/scripts/dev-test-integration.sh          # both integration suites; needs dev-up.sh
```

### What a new test may not do

Each of these is a bug that already happened, and each is now enforced rather
than remembered. If a guard is in the way, the test belongs in a different tier.

- **Do not stub the model provider yourself.** `STUDIO_REPLICATE_MODE=fake` is
  set autouse; the adapter answers all six of its functions locally. Every test
  that reached the engine used to monkeypatch it by hand, and a new file that
  forgot called Replicate for real.
- **Do not reach the network.** A socket guard allows loopback only in the unit
  suites, and blocks the provider hosts in the integration suites. The unit
  suite once made live calls to `api.replicate.com` and depended on them 401-ing.
- **Do not write to the repo.** `registry.PATH` is redirected at a per-test copy:
  `studio models refresh` rewrites the committed `models.json`, and the dispatch
  test invokes every leaf command. It deleted 391 lines of schema.
- **Do not edit `cli_surface_reference.json` to make a test pass.** Regenerate it
  with `tests.contracts.update_cli_reference <command>`.
- **Do not capture an API fixture with `curl`.** `/api/reel` answers with
  presigned URLs; `frontend/e2e/fixtures/capture.py` scrubs them. A hand-rolled
  capture put an AWS access key id into git.
- **Do not skip a tree at module level.** A `pytest_collection_modifyitems` hook
  or a `test.skip(...)` that is not filtered skips everything — 373 backend tests
  once reported as 373 skips and exited 0.

### Coverage is measured and gates on nothing

`pytest-cov` on both Python suites, `@vitest/coverage-v8` on the frontend,
report-only in `studio-pr.yml`. First honest figures, 2026-08-27: **backend 88%,
pipeline 72%, frontend 36%** (low by design — `vite.config.ts` argues for it).

There is deliberately no `--cov-fail-under`. A threshold picked before anyone has
read a real number either sits below it and means nothing, or fires on unrelated
PRs until somebody deletes it. Ratchet from these once there is a trend.

**Aim by the numbers, not by intuition.** Two survey passes over this repo
produced different rankings and both were wrong: `storyboard.py` was already at
95% while `movies.py` — patched in two bug-fix PRs and with no test file — was at
56%. Coverage will not tell you a state machine decides correctly, though; the
panel table test in `test_storyboard.py` exists because #494 and #498 both
shipped while those lines were being executed by tests asserting nothing about
what they decided.

The detail lives beside the code: each suite's `tests/__init__.py` is its map,
`studio-code-pipeline` covers the pipeline's, and `frontend/e2e/README.md` covers
the browser one.

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

All three need working AWS credentials. Since August 2026 those are a long-lived
IAM access key — `[default]` in `~/.aws/credentials`, or `AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY` in the environment on a machine without a home directory
of its own. boto3 and the Terraform provider read that natively, so the
`aws configure export-credentials` export the root [CLAUDE.md](../CLAUDE.md)
used to require is gone. Running it out of habit is a no-op, not an error.
