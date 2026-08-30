# studio — infrastructure

Terraform for both halves of studio. **Two environments now**, and the second
one is recent: `prod`, with state in
`s3://andreas-services-terraform-state/studio/prod/terraform.tfstate`, and
`dev`, which is **per machine** — its state key carries the AWS account and a
persistent machine UUID
(`studio/dev/<account>/<machine-id>/terraform.tfstate`), so two developers, or
one developer's two machines, never collide.

This file used to say "one environment, `prod`", and that was the whole posture:
local development pointed at production. It does not any longer — see the root
[CLAUDE.md](../../CLAUDE.md) and `../CLAUDE.md`.

| Module | What it is |
|---|---|
| `catalog` | **The library.** The DynamoDB table that says what exists. |
| `media` | **The media bucket.** Bytes only; nothing lists it. |
| `auth` | Cognito user pool (admin-create-only) + secretless SPA client |
| `compute` | ECR repo, the API Lambda, and its IAM — the bucket, the table, *and* the provider token |
| `api_gateway` | REST API, Cognito authorizer, CORS gateway responses, stage |
| `callbacks` | **Where a finished generation is reported.** Its own HTTP API, a receiver Lambda, SQS + a DLQ, and — in prod only — the worker that closes the run. **Both environments.** |
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

**`studio-prod-catalog`**, `us-east-1`, on-demand. As of 21 Aug 2026 it holds
one library, one membership, 277 nodes (one of them the root) and 555 items —
seeded and verified against prod (#279).

The item count is the node count doubled, plus the library and the membership,
and that is the shape of the whole design rather than an accident:

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
followed by a write. The window is gone rather than narrowed, and being able to
make that check atomically is the whole reason the library is a database and not
a bucket.

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
on the base table — working perfectly while the reel, the subtree walk and "who
is in this library" all fail `AccessDenied`. That asymmetry is exactly the sort
that ships. `modules/compute` grants `<arn>` and `<arn>/index/*`; `/index/*`
rather than three literals, because every index projects `ALL` over the same
rows and a fourth index should not be a two-module change.

### What protects it, and what it is protecting against

The media bucket's guarantee is versioning plus a role with no
`s3:DeleteObjectVersion`, so every delete studio can perform is a tombstone it
cannot reach past. **Nothing equivalent exists for a row.** A move or a transfer
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
  matter here. (This list was longer: the `maintenance/` one-shots ran under the
  same key and are deleted, which narrows the surface without changing the
  argument.) (This used to say the
  *pipeline* ran under that login. Since #308 it does not; the risk is unchanged,
  because the human still does.) It is also the
  half PITR does not cover: PITR pays to recover, out of band, into a *new*
  table, by someone who first has to notice. This makes the delete fail instead,
  at the moment a person can still change their mind. Turning it off is an
  in-place update, so a genuine teardown is a deliberate two-step rather than a
  blocked one.
- **No `Scan` and no `BatchWriteItem` in the Lambda's grant.** A Scan crosses
  library boundaries by construction, which is the one boundary the API exists
  to enforce. A batch is the wrong shape for the single bulk operation in the
  model — a move rewriting `path` on every descendant is precisely the write
  that must not half-apply.

**A lost row is a lost file even though every byte of it survives.** `blob_key`
is opaque, nothing derives it, and no listing of the bucket can reconstruct
which node a `blobs/<node_id>` object belonged to. That sentence is the reason
this table carries more protection than the bucket does, and it is worth
re-reading before anyone proposes relaxing either.

### Changing the table name is not a rename

`table_name` is composed by the environment (`[project]-[env]-[component]`), not
a literal in the module. Changing it on a live table is a destroy-and-recreate
that takes every row with it — the bytes in the media bucket survive and nothing
can name, place or reach them again. The bucket rename below is the precedent
for how much that costs; a table has no equivalent of "copy the current objects
across", because there is no second address to copy to that is not itself the
new table.

---

## The media bucket

**`studio-prod-media-us-east-1`**, `us-east-1`. 938 current objects and 1.26 GB
of generated media as of the August 2026 rename, and **there is no second copy
of it anywhere.** Versioning and `prevent_destroy` are the whole of its
protection.

It was renamed from `xharness-prod-media-us-east-1` in August 2026 — see
[The rename](#the-rename), which also records what the rename cost.

Counting the version history it is 2,572 versions and 2.75 GB, across 1,677
distinct keys — 718 of which exist only behind a delete marker. That gap between
959 and 1,677 is the whole reason the rename is a copy rather than a move.

Those are a snapshot (18 Aug 2026) and they move on their own. Curating a
character copies files from `corpus/` to `archive/` and deletes the originals,
so ordinary use pushes current-object count down and delete-marker count up
without anything being lost. Re-measure before relying on them.

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

### The rename

The convention is `[project]-[env]-[component]-[region]`. The bucket was
`xharness-prod-media-us-east-1`, created from a separate `xharness` repo before
studio absorbed the pipeline. It was renamed in August 2026.

**S3 has no rename.** Changing the `bucket` argument is a destroy-and-recreate,
and Terraform runs the destroy half against prior state, so `force_destroy`
added in the same apply is not even read. For a bucket holding the only copy of
the generated media, that is not an operation to attempt. The rename was
therefore a **second bucket and a copy**, in three applies:

| Step | Apply |
| --- | --- |
| 1 | `moved` block: `module.media` → `module.media_archive`. State edit only. |
| 2 | Create `module.media` — the new bucket, empty. |
| — | Copy the current objects across, server-side, and verify. |
| 3 | Re-point the IAM policy, the skills, backend, tests and docs. |

The copy was verified before anything was re-pointed: 938 keys,
1,261,751,658 bytes, every key present, every size equal, every ETag equal. Two
traps had to be handled for that comparison to mean anything:

- `aws s3 sync` **skips zero-byte keys ending in `/`**, so a folder marker did
  not copy — and being zero-byte, the byte totals still matched exactly. The
  object count caught it; a size check never would have.
- `sync` **uses multipart copy above 8 MB**, and a multipart ETag is an
  MD5-of-MD5s that cannot be compared with a single-part MD5. That left 29
  objects reading "different" at identical sizes. They were re-copied
  single-part so the checksums compare directly rather than being waved through.

Two other things bit, both worth knowing before the next migration:

- A `moved` block **breaks any `-target`ed apply** whose target set excludes the
  moved resources — "Moved resource instances excluded by targeting". The
  `bootstrap-ecr` job did exactly that and took every studio deploy down with
  it, naming ECR while the cause was an S3 module rename. That job now skips
  itself once the repository exists.
- `XHARNESS_S3_*` became `STUDIO_S3_*` in the same commit as the cutover, which
  was load-bearing rather than tidiness. `dev-setup.sh` writes the variable only
  when it is *absent*, so an existing `.env` would have kept a pinned
  `XHARNESS_S3_BUCKET` naming the old bucket and quietly kept writing there.
  Renaming the variable makes a stale line inert instead of wrong.

### What the rename cost

The old bucket was deleted in August 2026, on an explicit decision, once the
copy was verified. **Deleting it destroyed data that existed nowhere else:**

- 1,662 noncurrent object versions (1.51 GB) — every prior revision of every
  file that had ever been overwritten
- 767 keys recoverable only behind a delete marker — files deleted by curate
  runs and the app's tidy-up actions, restorable right up until the bucket went

Copying current objects moves 938 of roughly 1,700 keys that had ever existed.
The rest was history, and history is what a copy does not carry. That is the
part worth remembering: it was not visible in any listing, the app looked
completely intact without it, and it was still the entire "an overwrite or a
delete is recoverable" property that versioning on the bucket existed to
provide.

The live bucket is now versioned with no second copy behind it. A delete there
is recoverable only from its own version history, and that history has no
backstop.

### How it got into this state

It was imported, not created. In August 2026 the pipeline moved into `studio/`
and the bucket moved with it: `modules/media` was written to match the live
resource exactly, the five resources were imported into `studio/prod`, and the
plan was verified to contain no create, delete or replace before anything was
applied. The only change applied was tags (`Project: xharness` → `studio`).

The old repo's Terraform kept **local** state on one laptop. That is the problem
this fixed.

---

## The layout inside it

The tree lives at the **bucket root** — there is no wrapper prefix. (There was a
`media/` one, from when this mirrored a Google Drive folder 1:1; it bought
nothing and was removed. When it went, studio's browsable root was hard-coded to
it in five places and every listing silently came back empty, because a prefix
that matches nothing is not an error to S3.)

Three prefixes, and a key is three segments:

```
s3://studio-prod-media-us-east-1/
  characters/<char id>/<node id>.<ext>    bytes owned by a character
  projects/<proj id>/<node id>.<ext>      bytes owned by a project
                                          (runs, scenes, movies, inputs)
  libraries/<lib id>/<node id>.<ext>      owned by neither: the angle images,
                                          and anything loose under the root
  phrasebook/wording.yaml                 one legacy object, no row. See below.
```

**This section used to draw a folder tree here** — `characters/<name>/` holding
`profile.yaml` and `reference/`, `projects/<project>/` holding `runs/` and
`scenes/`, plus a top-level `config/angle/` and a `blobs/<node id>`. **None of
that is in the bucket.** It was the pre-catalog layout, where a key was a path
and the bucket was the index; the entity model made a record name a node id, and
`catalog migrate` then `reseat` rewrote production out of it. There are no
slug-shaped keys left, no `blobs/` and no top-level `config/`.

The tree a person browses is real and is the **catalog's**, not the bucket's —
`../docs/ENTITY_MODEL.md` draws it. S3 has no directories, nothing is ever listed
to find out what exists, and a key is reached only by following a row's
`blob_key`.

**A key carries two ids and nothing else, which is hard rule #1 applied to the
one place that had been quietly breaking it.** No slug, no folder path, no
filename — a listing of this bucket names no character and no project. The
extension is decoration for whoever opens the S3 console; `content_type` on the
row is authoritative.

**It is a pointer, not an address.** A rename does not touch it, a move does not
touch it, and nothing outside the API's `services/catalog.py` may split one on
`/`. The prefix is an operational convenience — per-entity cost in Storage Lens,
a lifecycle rule, a bulk delete that is one prefix.

**One shape is stamped and a second is still in the bucket.** `blob_key_for`
writes the three-segment key above. Between those and today the key was briefly
*descriptive* — `<entity>/<id>/<folders>/<filename>` — and a `reseat` wrote 181
production keys in that shape before it was reverted; the filename put character
names back into a listing, which is the leak the prefix scheme exists to close.
They are correct and readable where they sit, and a `reseat` clears them.
`../docs/ENTITY_MODEL.md` has the whole argument.

**#335 is still open and has been overtaken by events.** It asks for legacy keys
to be normalised; the migrator did it, and a listing today has none of what it
was filed about. What is left to normalise is the descriptive 181, which is the
same command.

Rows and blobs are still deleted separately, but a blob can no longer outlive
every row that named it unnoticed. `studio catalog gc` (#318) used to be the only
way to find one, by listing the bucket against the table. The API records the
keys a delete is about to free on a `SWEEP#` row before it frees them, and the
next delete finishes anything an interrupted one left — so the orphan is
addressed rather than searched for, and the command is deleted. See
`backend/studio_core/services/manage.py`.

**Shared material has rows now, and that is what emptied the raw `config/`
prefix.** The angle images are ordinary nodes in a `config/` folder the
library is created with, so their bytes are `libraries/<lib id>/…` like anything
else the library owns. `studio/config/` in source control stays their source of
truth and the library holds a copy, because a model may only be handed a
presigned URL of a stored object; `scripts/dev-shared-material.sh` pushes them
through `studio config sync` and no longer writes to the bucket itself. Nothing
in Terraform creates or owns them. The nodeless `config/angle/…` objects that
predated this were deleted in August 2026, deliberately and by hand. `catalog
gc` would not have collected them — `config/` was never in its allowlist — which
is why it had to be by hand.

`phrasebook/wording.yaml` is the one object left with no row, and nothing writes
it any more: the phrasebook is `TERM#<model>#<avoid>` rows, so there is no
document to seed and `studio phrasebook add` works against a library that has
never held one. It survives because deleting it buys nothing, and nothing sweeps
it: the collector that would once have had to be told to leave it alone no longer
exists, and the sweep rows that replaced it name only keys a delete actually
freed.

A project's material may involve several characters, so a character name is never
part of a production key — and since the key carries ids only, that now holds by
construction rather than by convention. Each run records which characters it
used. See [../docs/PIPELINE.md](../docs/PIPELINE.md) for what lives in a run, a
scene and a movie.

`media_root_prefix` is `""` (the whole bucket) and is the first knob that
matters if the layout is ever reshaped again. It narrows the API, the Lambda's
IAM policy and the bucket module together.

---

## The per-machine dev environment

Studio ran **local against prod** until August 2026 — one bucket, one pool, no
seed data — on the reasoning that an empty second bucket would exercise none of
the behaviour that matters. That reasoning was correct and is answered rather
than abandoned: the dev stack is *seeded* from a published fixture, so it is not
empty and is not a copy of anyone's production library. See #287, and the root
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
```

**The last two are the exception to "this environment declares no Lambda and no
API Gateway", and they earn it for one reason: Replicate cannot reach
`http://localhost:8000`.** Generation happens in the API now and a prediction is
closed by a callback, so without a public endpoint per machine the webhook path
could not be exercised on a developer's machine at all — local development would
poll, and the code that closes a run in production would be code nobody had ever
run.

What keeps it cheap is that **the deployed half is trivial and the half that
changes is not deployed.** The receiver is one dependency-free file, packaged by
Terraform as a zip straight out of `backend/` — no ECR, no image build, no
deploy step — and all it does is put the callback on the queue. `dev-up.sh` then
runs a consumer that long-polls that queue and closes the run with the working
tree. An apply is still seconds.

A stack applied before this landed has neither, and everything else about it
works: `dev-up.sh` says so once and a finished generation waits for `studio runs
reconcile <run>`.

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

`auth` and `dev_storage`, and nothing else. No hosting, no CloudFront, no API
Gateway, no custom domain, no ECR, no Lambda. The dev backend is Flask on `:8000`
under `dev-up.sh` and the SPA is Vite on `:5173`, both talking to real AWS
resources — a per-machine CloudFront distribution would cost twenty minutes per
apply and per destroy to prove nothing.

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
`backend/tests/test_cors_agreement.py` asserts both out of the Terraform. No
`GET` in either, and no `*` origin in either — a wildcard would let any page a
signed-in user visits complete a PUT whose URL it had obtained.

**`force_destroy` is set at creation and must never be retrofitted.** Terraform
applies the destroy half of a replacement against *prior state*, so the provider
reads the flag recorded in state and never sees a `true` added in the same
apply. A dev bucket that picks up objects before it picks up the flag is one only
an out-of-band empty-then-delete can remove. Same rule as the root
[CLAUDE.md](../../CLAUDE.md); the bucket rename above is what proved it.

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

`dev-aws-seed.sh` is in the list because that is where it belongs, not because
it works: `v1` is published and it loads. #284 landed
the publisher; nobody has run it. It is listed after `dev-user.sh` because the
library it writes needs a member, and the `sub` comes from the dev pool.

```bash
./studio/scripts/dev-aws-reset.sh --dry-run          # what a reset would remove
./studio/scripts/dev-aws-destroy.sh                  # tear it down; the machine id is kept
```

`dev-setup.sh` reads the stack's Terraform outputs — **not SSM**, which holds
what the deploy workflow wrote and knows nothing about a dev stack — and writes
`frontend/.env.local` plus pinned `STUDIO_S3_BUCKET` and `STUDIO_CATALOG_TABLE`
lines in `studio/.env`. It runs from the SessionStart hook and tolerates a
missing stack, warning and carrying on. `dev-up.sh` does not: an API with no
Cognito pool 500s on every call, so failing early is the faster way to find out.

> **What you get today is a seeded stack.** The bucket, the table and the pool
> are provisioned, `v1` is published, and `dev-aws-seed.sh` loads it in about
> two seconds — one character and its seed pool. This block used to say the
> opposite, in the same words, for as long as nobody had run `dev-seed
> publish --apply`. `dev-aws-reset.sh` empties a stack and does not re-seed; run
> the loader again afterwards.
>
> What *is* there is what `dev-setup.sh` pushes: the angle images under
> `config/`, and — since #425 — a starting `phrasebook/wording.yaml`, copied
> from the repo when the key is absent so `studio phrasebook add` works on a
> fresh stack. Neither has a catalog node, so neither shows the library
> populated; the table is still empty.

## The seed bucket

**Applied, and empty.** `studio-dev-seed-us-east-1` exists —
`arn:aws:s3:::studio-dev-seed-us-east-1`, `us-east-1`, confirmed by
`head-bucket` on 2026-08-22. It is `modules/dev_seed`, wired into
`envs/prod/main.tf`, so CI applied it alongside a later change under
`studio/infra/`.

This section twice said otherwise. It first said "declared, never applied — the
bucket still does not exist", written before that deploy and then believed
rather than rechecked. Correcting it, the next version refused to claim
anything either way and pointed at `terraform state list`. That was honest but
it is not what a reference is for: one `head-bucket` settles it, and a document
that declines to answer its own question makes every reader run the same
command. The lesson worth keeping is the first one — **an existence claim about
infrastructure rots the moment CI runs, so date it or check it.**

**`v1` was published on 2026-08-27**, which is the first time anything was —
`studio/fixtures/dev-seed/v1/` is in this repo and `scripts/dev-aws-seed.sh`
loads it in about two seconds. The paragraph above is about the BUCKET's
existence and still reads as it did; this one used to say the fixture had never
been published and no longer can. Taking the lesson at its word: dated, and
checked. What changed with #284 is that the
design is code rather than a comment in `modules/dev_storage/main.tf` describing
a bucket nobody had written.

**Why `envs/prod` owns it.** Its name says `dev` because that is who it serves;
the root says prod because that is the only studio root with an account-level
lifecycle. `envs/dev` is per machine and `dev-aws-destroy.sh` tears it down — a
bucket every developer's stack is seeded from must be out of reach of a
teardown. A third root would have been the tidier home and nothing applies it,
which is how the bucket stayed a design note for as long as it did. The
`Environment` tag is overridden to `dev` in the module block so the tag and the
name cannot disagree.

What it is for: **one shared fixture, published once, downloaded per machine**
(#284, #285). Real model output chosen to exercise the shapes the app cares
about — stills at two or three aspect ratios, one short video, a run folder with
`request.json` and `result.json`, a folder three deep, one deliberately awkward
name, an empty folder. Six to eight objects; every machine downloads it. Never a
copy of anyone's production library, which is the point that distinguishes this
from the old "just point at prod" arrangement and the reason it can be shared at
all.

Its posture, and what each decision is actually protecting:

- **One bucket for the account, not one per machine.** The whole value is that
  every developer's stack is seeded from the same bytes; a per-machine copy
  would be N copies of a fixture that never changes.
- **Versioned**, unlike the dev buckets it feeds. It is the *only* copy of a
  fixture that someone curated by hand, so it has the property the dev media
  buckets are allowed to lack — and it is small enough that the history costs
  nothing. Concretely it protects against a re-publish of `v1/` overwriting good
  bytes in place: the `v1/media/…` keys are stable across publishes of the same
  version, so a mistaken `--apply` replaces rather than adds.
- **No `force_destroy`, and `prevent_destroy` on top.** It outlives every dev
  stack that reads it, and there is no upstream to re-fetch it from — re-curating
  a fixture means driving a dev stack through a session of generations again,
  which costs money. `terraform destroy` on `envs/prod` already failed by design
  because of the media bucket; this is a second reason. The price is stated
  rather than discovered: **renaming this bucket later is an out-of-band
  empty-then-delete**, because the root [CLAUDE.md](../../CLAUDE.md)'s rule is
  that `force_destroy` is set at creation or never, and this is the creation.
- **All four public-access blocks on, ACLs off, SSE-S3.** Nothing here is
  public; `dev-aws-seed.sh` reads it with the developer's own AWS login.
- **One lifecycle rule**, aborting incomplete multipart uploads after seven
  days — a fixture carries a video, and an interrupted `cp` bills for parts no
  listing shows. Noncurrent versions are deliberately *not* expired: the
  versioning above is the recovery, and a fixture is touched a few times a year,
  so a 30-day rule would remove the recovery on exactly the timescale nobody
  notices.
- **Write is a deliberate promotion, read is ordinary** — but *today that is
  procedure, not IAM.* There is one human principal in this account and it both
  publishes and seeds, so there is no bucket policy and no read-only role: what
  makes a write deliberate is that `dev-seed publish` is a dry run unless
  `--apply` and refuses without an explicit attestation. The day a second
  developer gets an identity of their own is the day the read-only bucket policy
  goes into `modules/dev_seed`.

### Putting a fixture in

`dev-seed publish` (`scripts/dev_seed/`). It **promotes**
a fixture out of a dev stack rather than building one: a human drives the CLI
against their own stack as ordinary work, and a handful of the nodes that
produces become the fixture. So it calls no model, needs no provider token, and
carries no approval gate of its own — the approval happened when the generations
were run. `scripts/dev_seed/`'s own test pins that, and says what the pin
cannot see.

It reads the source stack's **catalog table**, not a bucket listing, and walks
`parent_id` to build each node's path — the API mints `node-<uuid4>` at random,
so a dev stack's ids are derived from nothing. **The fixture therefore carries no
ids at all**: `dev-aws-seed.sh` derives them as `uuid5` over
`s3://<dev bucket>/<path>`, with the bucket name inside the derivation, so two
machines get different ids from one fixture and that is correct.

Promotion is selective by construction. `--path` is required and repeatable,
there is no `--all`, a folder brings its subtree, ancestors are added because
the loader refuses a fixture whose parent folders are missing, and
`--max-objects` caps what the expansion can reach. Refusing to publish
everything is the default, not an option.

`catalog.json` lands in git, so **hard rule #1 applies to the promotion itself**
— in its env-scoped form, which is what made publishing possible at all. A dev
subject may be named in the repo; a production character may not. Two guards,
different in kind:

- **`source()`** refuses a bucket or table whose name contains `prod` before it
  reads anything, so a fixture is dev-origin by construction.
- **`name_problems`** refuses a stack holding any entity root outside
  `DEV_SUBJECTS`, a committed frozenset in `dev_seed.py`. The whole stack, not
  just the selection, because #284 is explicit that generating naturally and
  sanitising afterwards is the wrong order.

It reports the capitalised tokens found in promoted text and requires
`--dev-subjects-only` before `--apply`.

**This used to be two regexes** — a shape test (`subject-a`, `demo`, `<word>`)
plus a refusal on any Title Cased segment — and both are deleted. They could not
tell `mira` from `demo`, which the old `name_problems` docstring said outright,
so they admitted every lowercase first name and refused every capitalised folder.
An allowlist is a worse fit for a machine and a much better fit for the decision:
adding a subject is a reviewed diff, and that review is where "should this
likeness be in a fixture every machine downloads" gets asked. What it still
cannot catch is written out in `name_problems`, and the short version is that a
face is not text.

### The two documents

`v1/catalog.json` and `v1/manifest.json`. **The contract is that they are
authoritative in `studio/fixtures/dev-seed/<version>/`** — `FIXTURE_DIR` in
`dev_seed.py` — and copied into the bucket byte-identical for the loader, so
`catalog.json` is reviewable in git before anything reaches a machine. That
directory is not in the repo today: the first `publish --apply` is what creates
it, so read this as the contract it is rather than somewhere to go and look. `dev-aws-seed.sh`'s header specifies them field by field — it
shipped first and its author constructed the schema because #284 only sketched
it. That contract is no longer one-sided: `test_dev_seed.py` feeds the
publisher's output through the loader's own `fixture_problems` shell function, so
a disagreement about a field is a red test rather than a fixture rejected on
somebody's machine. Neither side needed changing to make them agree.

`v1/` is a version **prefix**, not object versioning: a fixture change is
additive and a machine is re-seeded to a known revision by naming `v2/`.

One thing is worth saying plainly: **`v1` exists, and everything above was
written before it did.** It carries one character and its seed pool — 54 stills,
12.4 MB, 59 nodes and one entity row.

What it does NOT carry is the rest of #284's list: a run folder with
`request.json` and `result.json`, a short video, a folder three deep. Those are
model output and cost money to generate, so the shapes the app's run, scene and
movie surfaces care about are still unexercised by a fresh stack. Adding them is
a `v2/` prefix, which is additive by design — that is what the version prefix is
for.

Publishing it also found three defects in `dev-aws-seed.sh` that had survived
since #285 landed, all for the same reason: the script had never run past its
first read. The angle image push ran before the library it needs existed, an entity
record went in without the `id` every read indexes on, and the bytes moved one
`aws s3 cp` per object — 564 seconds for 54 of them, now 71.

---

## Reaching the media by hand

**Do not.** This section used to be three `aws s3 presign` / `aws s3 cp` lines
against `studio-prod-media-us-east-1`, and every one of them is now the wrong
instruction for two independent reasons:

- **A raw `cp` puts bytes in the bucket and writes no row**, so the file is
  invisible to the app and to every `studio` command, and `catalog gc` will
  eventually offer to delete it as an orphan. The tree in the bucket is not the
  library any more; the table is.
- **They named the prod bucket.** Local work runs against this machine's dev
  stack, so a command copied out of this file writes to production from a
  laptop — the exact arrangement #287 removed.

Use the `studio-media-s3` skill, which goes through the API: it mints the row
and the presigned PUT together, and it knows that moving something means
rewriting the records that name it.

What is still true, and is the reason presigning exists at all: **the bucket is
private and must stay private.** Replicate only ever needs a fetchable HTTPS URL
for the duration of a job, so it gets a short-lived presigned URL and never
credentials, and never bytes uploaded from disk. All four public-access blocks
stay on.

For read-only investigation of *prod* — which is a legitimate thing to want —
the deployed app at `studio.andreas.services` reads it, and a
`aws dynamodb query` against `studio-prod-catalog` answers questions a bucket
listing cannot. Running the **CLI** against prod is still wanted occasionally
and the safe mechanism is deliberately undecided; do not invent one here.

---

## Running Terraform locally

Rarely needed; CI owns the apply. No credential export is needed: the access key
in `~/.aws/credentials`, or `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in the
environment, is read by the AWS **provider** and the S3 **backend** alike. Under
the `aws login` sessions this replaced in August 2026 only the backend resolved,
so `state list` worked while `plan` and `apply` failed with a misleading IMDS
error — the root [CLAUDE.md](../../CLAUDE.md) keeps that history, because the
error text has not changed and now means something else.

```bash
terraform -chdir=studio/infra/envs/prod plan
```
