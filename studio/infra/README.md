# studio — infrastructure

Terraform for both halves of studio. **Two environments**: `prod`, with state in
`s3://andreas-services-terraform-state/studio/prod/terraform.tfstate`, and
`dev`, which is **per machine** — its state key carries the AWS account and a
persistent machine UUID
(`studio/dev/<account>/<machine-id>/terraform.tfstate`), so two developers, or
one developer's two machines, never collide. Local development points at the
dev stack, never at production — see the root [CLAUDE.md](../../CLAUDE.md) and
`../CLAUDE.md`.

| Module | What it is |
|---|---|
| `catalog` | **The library.** The DynamoDB table that says what exists. |
| `media` | **The media bucket.** Bytes only; nothing lists it. |
| `auth` | Cognito user pool (admin-create-only) + secretless SPA client |
| `compute` | ECR repo, the API Lambda, and its IAM — the bucket, the table, *and* the provider token |
| `api_gateway` | REST API, Cognito authorizer, CORS gateway responses, stage |
| `callbacks` | **Where a finished generation is reported.** Its own HTTP API, a receiver Lambda, SQS + a DLQ, and — in prod only — the worker that closes the run. **Both environments.** |
| `render` | **Where a scene is cut.** SQS + a DLQ, a **second** ECR repo, and — in prod only — a worker Lambda running an image that carries `ffmpeg`. Its own execution role, unlike the callback worker's. **Both environments** (dev gets the queue and drains it from a laptop). |
| `api_domain` | `studio-api.andreas.services` custom domain + Route53 record |
| `hosting` | The SPA's S3 bucket, CloudFront, OAC, SPA-fallback function |
| `dev_storage` | **dev only.** `media` + `catalog` with every guard removed |
| `dev_seed` | **the shared fixture bucket.** Versioned, undeletable, one per account |

**`catalog` is listed first because it is the one that matters.** Everything
else in this directory is reconstructible: the ECR image from git, the SPA
bundle from a build, the pool from an apply plus `create-user.sh`. The table is
not, and neither is the bucket — but they fail differently, and that difference
runs through the rest of this file.

`envs/prod` is applied by `.github/workflows/studio-prod.yaml`, not by hand;
`envs/dev` is the opposite and is **never applied by CI**. Both are covered in
[The per-machine dev environment](#the-per-machine-dev-environment) below, which
is also where `dev_storage` earns its existence. Read
[../docs/WEB_APP.md](../docs/WEB_APP.md) for the deploy DAG.

---

## The catalog

**`studio-prod-catalog`**, `us-east-1`, on-demand (`PAY_PER_REQUEST`), keyed
`pk` / `sk`.

```
Library      pk = LIB#<lib_id>        sk = META
Membership   pk = USER#<sub>          sk = LIB#<lib_id>
Node         pk = NODE#<parent_id>    sk = NAME#<name>     ← by parent
Node         pk = NODE#<node_id>      sk = META            ← by id
```

**A node is two items, so every write is a `TransactWriteItems`.** The by-parent
item makes a folder listable and makes a name unique inside it; the by-id item
is the record. There is no write that touches one without the other. A node that
exists under one key and not the other is a node that either cannot be listed or
cannot be opened, so a single `PutItem` anywhere in this model is a bug.

That is also what buys the 409. A name collision is a **condition failure** —
the `NAME#` item goes in under `attribute_not_exists(pk)` — never a read
followed by a write. Being able to make that check atomically is the whole
reason the library is a database and not a bucket.

Three GSIs, all `projection_type = ALL` over the same rows:

| Index | Keys | Answers |
|---|---|---|
| `by-sk` | `sk` / `pk` | "who is in library X" — the reverse of the membership row |
| `by-path` | `lib` / `path` | a whole subtree in one `begins_with` |
| `by-recent` | `reel` / `created_at` | newest-first across a library, genuinely paginated. **Sparse** — `reel` is written only onto image and video file nodes, so folders and entity rows stay out of the enumeration |

`path` is a materialised list of ancestor ids (`/node-a/node-b/`) and is
**derived**: `parent_id` is authoritative, a move rewrites `path` across every
descendant, and an interrupted move leaves a stale `path` that can be rebuilt
from `parent_id`. Nothing can rebuild `parent_id`, which is why it is written
first.

**Naming the index ARNs in the IAM policy is not optional.** DynamoDB authorises
a Query against the index it names, not against the base table, so
`resources = [<arn>]` alone leaves a plain folder listing — `pk = NODE#<parent>`
on the base table — working perfectly while the feed, the subtree walk and "who
is in this library" all fail `AccessDenied`. `modules/compute` grants `<arn>`
and `<arn>/index/*`; `/index/*` rather than three literals, because every index
projects `ALL` over the same rows and a fourth index should not be a two-module
change. `backend/tests/unit/test_iam_agreement.py` reads the grant out of the
Terraform.

### What protects it, and what it is protecting against

The media bucket's guarantee is versioning plus a role with no
`s3:DeleteObjectVersion`, so every delete studio can perform is a tombstone it
cannot reach past. A lifecycle rule expires a noncurrent version after 30 days
(`noncurrent_version_expiration_days`) and removes a delete marker with nothing
behind it, so the recovery window is bounded rather than the bucket growing
with every overwrite. **Nothing equivalent exists for a row.** A move or a transfer
rewrites `path` or `lib` across a whole subtree, in place, and leaves nothing
behind. So:

- **PITR on, 35 days, restorable to any second.** It is the only recovery this
  data has. The variable defaults to `true` and the asymmetry is deliberate:
  forgetting it costs the library, enabling it needlessly costs cents a month on
  a table of metadata for a few thousand files. An environment that genuinely
  does not want it has to say so — which `envs/dev` does.
- **`deletion_protection_enabled`, and it is not a duplicate of
  `prevent_destroy`.** `prevent_destroy` is a Terraform lifecycle guard: it
  errors at plan time, so a `terraform destroy` over this state fails. It says
  nothing about a `-target`ed destroy of this table alone, a console click, or a
  stray CLI call — and there is a human in this account whose access key runs
  Terraform, `dev-seed` and the `dev-aws-*` scripts, so those are the paths that
  matter. It is also the half PITR does not cover: PITR pays to recover, out of
  band, into a *new* table, by someone who first has to notice. This makes the
  delete fail instead, at the moment a person can still change their mind.
  Turning it off is an in-place update, so a genuine teardown is a deliberate
  two-step rather than a blocked one.
- **No `Scan` and no `BatchWriteItem` in the Lambda's grant.** A Scan crosses
  library boundaries by construction, which is the one boundary the API exists
  to enforce. A batch is the wrong shape for the single bulk operation in the
  model — a move rewriting `path` on every descendant is precisely the write
  that must not half-apply.

**A lost row is a lost file even though every byte of it survives.** `blob_key`
is opaque, nothing derives it, and no listing of the bucket can reconstruct
which node an object belonged to. That sentence is the reason this table
carries more protection than the bucket does, and it is worth re-reading before
anyone proposes relaxing either.

### Changing the table name is not a rename

`table_name` is composed by the environment (`[project]-[env]-[component]`), not
a literal in the module. Changing it on a live table is a destroy-and-recreate
that takes every row with it — the bytes in the media bucket survive and nothing
can name, place or reach them again. A table has no equivalent of "copy the
current objects across", because there is no second address to copy to that is
not itself the new table.

---

## The media bucket

**`studio-prod-media-us-east-1`**, `us-east-1`, and **there is no second copy
of it anywhere.** Versioning and `prevent_destroy` are the whole of its
protection. A delete there is recoverable only from its own version history,
and that history has no backstop.

- **Private.** All four public-access blocks on, ACLs disabled
  (`BucketOwnerEnforced`). Objects reach Replicate and the browser only as
  short-lived presigned URLs, which work with every one of those flags on.
- **Versioned**, and this is load-bearing rather than hygiene. Curating a
  character rewrites objects in place and the app's tidy-up actions delete them;
  both are recoverable only because prior revisions survive. The API's role has
  no `s3:DeleteObjectVersion`, so every delete it can perform is a tombstone it
  cannot then reach past.
- **Encrypted** at rest (SSE-S3 / AES256, bucket key on).
- **`prevent_destroy`.** Note the blast radius: this blocks `terraform destroy`
  on the *entire* `studio/prod` state, which is intended. Tearing studio down
  means removing `module.media` from state first, deliberately. There is no
  `force_destroy` either, so S3 refuses to delete it while it holds anything.
- **One CORS rule**: `PUT` with `content-type` and `content-length`, from the
  SPA's origin. See [the dev environment](#why-dev_storage-is-a-third-module-rather-than-a-flag)
  for why both buckets carry it.

**Do not change `media_bucket_name` to rename the bucket.** S3 has no rename:
a changed name is a destroy-and-recreate, and Terraform runs the destroy half
against prior state, so a `force_destroy` added in the same apply is not even
read. Renaming means a second bucket, a verified server-side copy, and a
re-pointed policy — and a copy carries current objects only, never the version
history. That is the reason the current bucket has no history behind it: it
was itself renamed into existence in August 2026 and its predecessor deleted.

---

## The layout inside it

The tree lives at the **bucket root** — there is no wrapper prefix. Three
prefixes, and a key is three segments:

```
s3://studio-prod-media-us-east-1/
  characters/<char id>/<node id>.<ext>    bytes owned by a character
  projects/<proj id>/<node id>.<ext>      bytes owned by a project
                                          (runs, scenes, movies, inputs)
  libraries/<lib id>/<node id>.<ext>      owned by neither: the angle images,
                                          and anything loose under the root
```

The tree a person browses is real and is the **catalog's**, not the bucket's —
`../docs/ENTITY_MODEL.md` draws it. S3 has no directories, nothing is ever
listed to find out what exists, and a key is reached only by following a row's
`blob_key`.

**A key carries two ids and nothing else, which is hard rule #1 applied to the
one place that could otherwise break it.** No name, no folder path, no
filename — a listing of this bucket names no character and no project. The
extension is decoration for whoever opens the S3 console; `content_type` on the
row is authoritative.

**It is a pointer, not an address.** A rename does not touch it, a move does not
touch it, and nothing outside the API's `services/catalog.py` may split one on
`/`. The prefix is an operational convenience — per-entity cost in Storage Lens,
a lifecycle rule, a bulk delete that is one prefix. Move a file between
entities and the prefix goes stale while the key stays correct; nothing
corrects it, because nothing reads it.

Rows and blobs are deleted separately, but a blob cannot outlive every row that
named it unnoticed: the API records the keys a delete is about to free on a
`SWEEP#` row before it frees them, and the next delete finishes anything an
interrupted one left — so the orphan is addressed rather than searched for. See
`backend/studio_core/services/manage.py`.

**Shared material has rows.** The angle images are ordinary nodes in a
`config/` folder the library is created with, so their bytes are
`libraries/<lib id>/…` like anything else the library owns. `studio/config/` in
source control is their source of truth and the library holds a copy, because a
model may only be handed a presigned URL of a stored object;
`scripts/dev-shared-material.sh` pushes them through `studio config sync`.
Nothing in Terraform creates or owns them. The phrasebook is `TERM#` rows and
has no object at all.

A project's material may involve several characters, so a character name is
never part of a key — and since the key carries ids only, that holds by
construction rather than by convention. Each run records which characters it
used. See [../docs/PIPELINE.md](../docs/PIPELINE.md) for what lives in a run, a
scene and a movie.

---

## The per-machine dev environment

The dev stack is *seeded* from a published fixture, so it is not empty and is
not a copy of anyone's production library. See the root
[CLAUDE.md](../../CLAUDE.md).

The mechanism is a verbatim port of humbugg's, down to the state key layout, so
it is learned once and applies to both services.

### One stack per machine, keyed by a UUID

```
~/.config/andreas-services/studio/machine-id     a persistent lowercase UUID
studio-dev-<short12>-app                         Cognito pool + SPA client
studio-dev-<short12>-media-us-east-1             the dev media bucket
studio-dev-<short12>-catalog                     the dev catalog table
studio-dev-<short12>-callbacks                   the callback queue (+ -dlq)
studio-dev-<short12>-callback-receiver           the Lambda Replicate calls
studio-dev-<short12>-render                      the render queue (+ -dlq)
```

**The callback receiver is the exception to "this environment declares no
Lambda and no API Gateway", and it earns it for one reason: Replicate cannot
reach `http://localhost:8000`.** Generation happens in the API and a prediction
is closed by a callback, so without a public endpoint per machine the webhook
path could not be exercised on a developer's machine at all.

What keeps it cheap is that **the deployed half is trivial and the half that
changes is not deployed.** The receiver is one dependency-free file, packaged by
Terraform as a zip straight out of `backend/` — no ECR, no image build, no
deploy step — and all it does is put the callback on the queue. `dev-up.sh` then
runs `handlers/local/consumer/callback_consumer.py`, which long-polls that queue
and closes the run with the working tree. An apply is still seconds.

A stack applied without the callback module still works: `dev-up.sh` says so
once and a finished generation waits for `studio runs reconcile <run>`.

**The render queue is the same arrangement, one queue over, and it declares no
Lambda at all.** `envs/dev` passes `create_ecr = false` and `create_worker =
false`: a per-machine image build would cost minutes per apply, and the render
image is the larger of the two because it carries `ffmpeg`. So the queue exists
and `dev-up.sh` drains it with `handlers/local/consumer/render_consumer.py` — the
working tree, against `imageio-ffmpeg`'s bundled binary, which is the same
encoder prod runs. A stack with no render queue can browse and generate and
cannot stitch; `dev-up.sh` says so once and names the re-apply.

`<short12>` is the first twelve hex characters of the UUID. `dev-aws-common.sh`
computes it as `RESOURCE_PREFIX` and passes it in; `envs/dev` never generates
one, so a resource name and the file that named it cannot drift.

**The state key carries the account and the full UUID:**

```
s3://andreas-services-terraform-state/studio/dev/<account-id>/<machine-id>/terraform.tfstate
```

One bucket, and the *key* is what separates two developers — or one developer's
two machines — in a single shared AWS account. `backend.tf` therefore declares
the bucket and region and **no key**; `dev-aws-common.sh` supplies it as
`-backend-config="key=$STATE_KEY"` at init. A hard-coded key here would have two
machines silently sharing one state, and destroying it.

**The machine id is the only handle on the resources.** Lose it and the stack is
running, billing and unreachable — there is no listing that recovers it, because
the state it points at is the only record. `STUDIO_DEV_MACHINE_ID` targets a
stack this machine did not create, and `dev-aws-common.sh` persists whatever it
is given. Two cases need it: an ephemeral environment, where a generated id dies
with the container; and a second machine reaching an existing stack on purpose.

Every resource carries the repo's four tags plus `DeveloperMachineId`,
`DeveloperPrincipal` and `MachineName`. These live in the same account as prod
and outlive the terminal that created them — a stray dev bucket is found by its
tags or not at all.

### What `envs/dev` deliberately does not declare

`auth`, `storage` (`modules/dev_storage`), `callbacks` and `render`, and nothing
else. No hosting, no CloudFront, no REST API Gateway, no custom domain, no ECR,
no container Lambda. The dev backend is Flask on `:8000` under `dev-up.sh` and
the SPA is Vite on `:5173`, both talking to real AWS resources — a per-machine
CloudFront distribution would cost twenty minutes per apply and per destroy to
prove nothing.

`envs/prod` is applied by `.github/workflows/studio-prod.yaml`, never by hand.
`envs/dev` is the exact opposite: **never applied by CI**, only by
`scripts/dev-aws-setup.sh` on a developer's machine. No tfvars file is committed
for it — every variable comes from `dev-aws-common.sh`'s `set_terraform_vars`,
and the validations on `machine_id` and `machine_short_id` are what stop a
malformed id becoming a resource name nothing can find again.

### Why `dev_storage` is a third module rather than a flag

**`prevent_destroy` takes a literal, not a variable.** There is no
`prevent_destroy = var.is_prod`. So a bucket `dev-aws-destroy.sh` can actually
delete cannot come from the module that guards the prod one, and the alternative
— a `count`/`for_each` fork inside `modules/media` — would put the prod bucket's
protection one wrong variable away from being off. That is the trade this module
refuses. humbugg has a `dev_storage` for the same reason.

What `dev_storage` changes, and only this:

| | prod | dev |
|---|---|---|
| Bucket `force_destroy` | absent | **`true`, set at creation** |
| Bucket versioning | on, load-bearing | off |
| Bucket `prevent_destroy` | yes | no |
| Table PITR | on | off |
| Table deletion protection | on | off |

Private, ACLs off (`BucketOwnerEnforced`) and SSE-S3 are identical in both,
because matching prod costs nothing there.

**So is the CORS rule, and there it costs something to get wrong.** Both buckets
carry an `aws_s3_bucket_cors_configuration` allowing `PUT` with `content-type`
and `content-length` — exactly the two headers `s3.presign_put` puts in
`X-Amz-SignedHeaders` — because the app's upload is a presigned PUT the browser
sends straight to the bucket and therefore preflights. Only the origin differs:
`https://studio.andreas.services` against `dev-up.sh`'s `http://localhost:5173`.
A rule on one bucket and not the other is an upload that works in prod and fails
on every machine, which is the worst shape a prod/dev difference can take;
`backend/tests/unit/test_cors_agreement.py` asserts both out of the Terraform.
No `GET` in either, and no `*` origin in either — a wildcard would let any page
a signed-in user visits complete a PUT whose URL it had obtained.

**`force_destroy` is set at creation and must never be retrofitted.** Terraform
applies the destroy half of a replacement against *prior state*, so the provider
reads the flag recorded in state and never sees a `true` added in the same
apply. A dev bucket that picks up objects before it picks up the flag is one only
an out-of-band empty-then-delete can remove. Same rule as the root
[CLAUDE.md](../../CLAUDE.md).

Versioning is off in dev for a positive reason, not neglect: recovery in dev is
re-seeding, so version history would only slow `force_destroy` down (it has to
delete every version) and bill for bytes nobody will ever restore.

**The dev table's key schema and three indexes are a deliberate, exact copy of
`modules/catalog`.** That duplication is the price of the split above and it is
load-bearing — an index missing here is a query that passes locally and fails in
prod, or the reverse. If the two ever drift, `modules/catalog` is the source of
truth; mirror it back.

### Provisioning one

```bash
aws sts get-caller-identity                          # confirm the access key resolves
./studio/scripts/dev-aws-setup.sh                    # provision this machine's stack
./studio/scripts/dev-user.sh --generate-password     # its one test account
./studio/scripts/dev-token.sh                        # prove sign-in works; prints a token
./studio/scripts/dev-aws-seed.sh                     # load the fixture — see below
./studio/scripts/dev-setup.sh                        # write the env files, install toolchains
./studio/scripts/dev-up.sh                           # backend :8000, frontend :5173
```

`dev-aws-seed.sh` is listed after `dev-user.sh` because the library it writes
needs a member, and the `sub` comes from the dev pool.

```bash
./studio/scripts/dev-aws-reset.sh --dry-run          # what a reset would remove
./studio/scripts/dev-aws-destroy.sh                  # tear it down; the machine id is kept
```

`dev-setup.sh` reads the stack's Terraform outputs — **not SSM**, which holds
what the deploy workflow wrote and knows nothing about a dev stack — and writes
`frontend/.env.local` and the CLI's `dev` profile. It runs from the
SessionStart hook and tolerates a missing stack, warning and carrying on.
`dev-up.sh` does not: an API with no Cognito pool 500s on every call, so
failing early is the faster way to find out.

A freshly provisioned stack holds the shared material `dev-setup.sh` pushes —
the angle images under `config/` — and whatever `dev-aws-seed.sh` loads.
`dev-aws-reset.sh` empties a stack and does not re-seed; run the loader again
afterwards.

## The seed bucket

**`studio-dev-seed-us-east-1`** is `modules/dev_seed`, wired into
`envs/prod/main.tf` and applied by CI. `studio/fixtures/dev-seed/v1/` is in
this repo and `scripts/dev-aws-seed.sh` loads it in about two seconds — one
character and its seed pool.

**Why `envs/prod` owns it.** Its name says `dev` because that is who it serves;
the root says prod because that is the only studio root with an account-level
lifecycle. `envs/dev` is per machine and `dev-aws-destroy.sh` tears it down — a
bucket every developer's stack is seeded from must be out of reach of a
teardown. The `Environment` tag is overridden to `dev` in the module block so
the tag and the name cannot disagree.

What it is for: **one shared fixture, published once, downloaded per machine.**
Real model output chosen to exercise the shapes the app cares about, and never
a copy of anyone's production library — which is the reason it can be shared at
all.

Its posture, and what each decision is actually protecting:

- **One bucket for the account, not one per machine.** The whole value is that
  every developer's stack is seeded from the same bytes; a per-machine copy
  would be N copies of a fixture that never changes.
- **Versioned**, unlike the dev buckets it feeds. It is the *only* copy of a
  fixture that someone curated by hand, and it is small enough that the history
  costs nothing. Concretely it protects against a re-publish of `v1/`
  overwriting good bytes in place: the `v1/media/…` keys are stable across
  publishes of the same version, so a mistaken `--apply` replaces rather than
  adds.
- **No `force_destroy`, and `prevent_destroy` on top.** It outlives every dev
  stack that reads it, and there is no upstream to re-fetch it from — re-curating
  a fixture means driving a dev stack through a session of generations again,
  which costs money. The price is stated rather than discovered: **renaming
  this bucket later is an out-of-band empty-then-delete**, because the root
  [CLAUDE.md](../../CLAUDE.md)'s rule is that `force_destroy` is set at creation
  or never, and this is the creation.
- **All four public-access blocks on, ACLs off, SSE-S3.** Nothing here is
  public; `dev-aws-seed.sh` reads it with the developer's own AWS credentials.
- **One lifecycle rule**, aborting incomplete multipart uploads after seven
  days — an interrupted `cp` bills for parts no listing shows. Noncurrent
  versions are deliberately *not* expired: the versioning above is the
  recovery, and a fixture is touched a few times a year, so a 30-day rule would
  remove the recovery on exactly the timescale nobody notices.
- **Write is a deliberate promotion, read is ordinary** — but *today that is
  procedure, not IAM.* There is one human principal in this account and it both
  publishes and seeds, so there is no bucket policy and no read-only role: what
  makes a write deliberate is that `dev-seed publish` is a dry run unless
  `--apply` and refuses without `--dev-subjects-only`. The day a second
  developer gets an identity of their own is the day the read-only bucket
  policy goes into `modules/dev_seed`.

### Putting a fixture in

`dev-seed publish` (`scripts/dev_seed/`). It **promotes** a fixture out of a
dev stack rather than building one: a human drives the CLI against their own
stack as ordinary work, and a handful of the nodes that produces become the
fixture. So it calls no model, needs no provider token, and carries no approval
gate of its own — the approval happened when the generations were run.
`scripts/dev_seed/tests/test_dev_seed.py` pins that.

It reads the source stack's **catalog table**, not a bucket listing, and walks
`parent_id` to build each node's path — the API mints `node-<uuid4>` at random,
so a dev stack's ids are derived from nothing. **The fixture therefore carries no
ids at all**: the loader derives them as `uuid5` over
`s3://<dev bucket>/<path>`, with the bucket name inside the derivation, so two
machines get different ids from one fixture and that is correct.

Promotion is selective by construction. `--path` is required and repeatable,
there is no `--all`, a folder brings its subtree, ancestors are added because
the loader refuses a fixture whose parent folders are missing, and
`--max-objects` caps what the expansion can reach. Refusing to publish
everything is the default, not an option.

`catalog.json` lands in git, so **hard rule #1 applies to the promotion itself**
— in its env-scoped form. A dev subject may be named in the repo; a production
character may not. Two guards, different in kind:

- **`source()`** refuses a bucket or table whose name contains `prod` before it
  reads anything, so a fixture is dev-origin by construction.
- **`name_problems`** refuses a stack holding any entity root outside
  `DEV_SUBJECTS`, a committed frozenset in `scripts/dev_seed/dev_seed/seed.py`.
  The whole stack, not just the selection, because generating naturally and
  sanitising afterwards is the wrong order.

It reports the capitalised tokens found in promoted text and requires
`--dev-subjects-only` before `--apply`. What it still cannot catch is written
out in `name_problems`, and the short version is that a face is not text.

### The two documents

`v1/catalog.json` and `v1/manifest.json`. **They are authoritative in
`studio/fixtures/dev-seed/<version>/`** — `FIXTURE_DIR` in `seed.py` — and
copied into the bucket byte-identical for the loader, so `catalog.json` is
reviewable in git before anything reaches a machine. `dev-aws-seed.sh`'s header
specifies them field by field, and `test_dev_seed.py` feeds the publisher's
output through the loader's own `fixture_problems` shell function, so a
disagreement about a field is a red test rather than a fixture rejected on
somebody's machine.

`v1/` is a version **prefix**, not object versioning: a fixture change is
additive and a machine is re-seeded to a known revision by naming `v2/`. A run
folder, a short video and a deeply nested folder are model output and cost
money to generate, so `v1` does not carry them; adding them is a `v2/` prefix.

---

## Reaching the media by hand

**Do not.** A raw `aws s3 cp` puts bytes in the bucket and writes no row, so
the file is invisible to the app and to every `studio` command. The tree in the
bucket is not the library; the table is. And local work runs against this
machine's dev stack, so a command naming the prod bucket writes to production
from a laptop.

Use the `studio-media-s3` skill, which goes through the API: it mints the row
and the presigned PUT together.

What is still true, and is the reason presigning exists at all: **the bucket is
private and must stay private.** Replicate only ever needs a fetchable HTTPS URL
for the duration of a job, so it gets a short-lived presigned URL and never
credentials, and never bytes uploaded from disk. All four public-access blocks
stay on.

For read-only investigation of *prod* the deployed app at
`studio.andreas.services` reads it, and an `aws dynamodb query` against
`studio-prod-catalog` answers questions a bucket listing cannot. Running the
**CLI** against prod is `studio --profile prod <command>` — see `../CLAUDE.md`.

---

## Running Terraform locally

Rarely needed; CI owns the apply. No credential export is needed: the access key
in `~/.aws/credentials`, or `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in the
environment, is read by the AWS **provider** and the S3 **backend** alike — the
root [CLAUDE.md](../../CLAUDE.md) explains the failure signature when neither
is present.

```bash
terraform -chdir=studio/infra/envs/prod plan
```
