# studio — infrastructure

Terraform for both halves of studio. One environment, `prod`, with state in
`s3://andreas-services-terraform-state/studio/prod/terraform.tfstate`.

| Module | What it is |
|---|---|
| `media` | **The media bucket.** The asset store both halves share. |
| `auth` | Cognito user pool (admin-create-only) + secretless SPA client |
| `compute` | ECR repo, the API Lambda, and its IAM — including the bucket policy |
| `api_gateway` | REST API, Cognito authorizer, CORS gateway responses, stage |
| `api_domain` | `studio-api.andreas.services` custom domain + Route53 record |
| `hosting` | The SPA's S3 bucket, CloudFront, OAC, SPA-fallback function |

Applied by `.github/workflows/studio-prod.yaml`, not by hand. Read
[../docs/WEB_APP.md](../docs/WEB_APP.md) for the deploy DAG.

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

Two trees, because they are two different things:

```
s3://studio-prod-media-us-east-1/
  characters/<name>/          an IDENTITY record
      profile.yaml            the bible, including the described reference index
      reference/              generated character imagery, in purpose subfolders
      corpus/  seed/  archive/
  projects/<project>/         a piece of WORK
      project.json
      runs/  chains/  scenes/  movies/  favorites/  input/
  phrasebook/wording.yaml
  config/pose/                shared POSE PLATES — generic, no identity
```

`config/` is the only prefix whose source of truth is the repo rather than the
bucket: it is `studio/config/` in source control, and `dev-setup.sh` syncs it out
so a model can be handed a presigned URL of it. Nothing in Terraform creates or
owns it, and because `media_root_prefix` is `""` it is browsable in the app like
any other top-level folder.

A project's material may involve several characters, so a character name is
never part of a production key; each run records which characters it used. See
[../docs/PIPELINE.md](../docs/PIPELINE.md) for what lives in a run, a scene and
a movie.

`media_root_prefix` is `""` (the whole bucket) and is the first knob that
matters if the layout is ever reshaped again. It narrows the API, the Lambda's
IAM policy and the bucket module together.

---

## Reaching the bucket by hand

The bucket is private; do not make it public. Give Replicate a **presigned
URL** — short-lived, no credentials leaked — since it only needs a fetchable
HTTPS URL for the duration of the job.

```bash
aws s3 presign s3://studio-prod-media-us-east-1/characters/<name>/reference/face/<name>_1.webp --expires-in 3600
```

```bash
aws s3 cp ./<name>_1.webp s3://studio-prod-media-us-east-1/characters/<name>/reference/face/<name>_1.webp
```

```bash
aws s3 cp s3://studio-prod-media-us-east-1/projects/<project>/runs/<run_id>/output/clip.mp4 ./clip.mp4
```

Prefer the `studio-s3` skill over raw CLI for anything that touches a record — moving
an object means rewriting the records that name it, and the skill knows that.

---

## Running Terraform locally

Rarely needed; CI owns the apply. When you do, export credentials first — the S3
**backend** resolves an `aws login` session but the AWS **provider** does not,
so `state list` works while `plan` and `apply` fail with a misleading IMDS
error. The root [CLAUDE.md](../../CLAUDE.md) documents the split.

```bash
eval "$(aws configure export-credentials --format env)"
```

```bash
terraform -chdir=studio/infra/envs/prod plan
```
