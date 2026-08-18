# studio — infrastructure

Terraform for both halves of studio. One environment, `prod`, with state in
`s3://andreas-services-terraform-state/studio/prod/terraform.tfstate`.

| Module | What it is |
|---|---|
| `media` | **The media bucket.** The asset store both halves share. Instantiated twice — the live bucket and the retained archive. |
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
of generated media as of the August 2026 cutover.

It was renamed from `xharness-prod-media-us-east-1`, which is retained as the
archive — see [The rename](#the-rename). The archive is **not** a backup: it is
frozen at the cutover and nothing writes to it, so this bucket's own versioning
and `prevent_destroy` remain what protect current work.

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
1.27 GB of generated media, that operation does not get attempted. The rename is
therefore **a second bucket and a copy**, in three applies:

| Step | Apply does | Live bucket after |
| --- | --- | --- |
| 1 ✅ | `moved` block: `module.media` → `module.media_archive`. State edit only, zero AWS changes. | archive |
| 2 ✅ | Create `module.media` — the new bucket, empty. | archive |
| — ✅ | Copy the current objects across, server-side, and verify. | archive |
| 3 ✅ | Flip `local.active_media`, and re-point the skills, backend, tests and docs. | **new** |

Steps 1 and 2 cannot be one apply: Terraform refuses to declare `module.media`
while a `moved` block still names it as a source.

`local.active_media` in `envs/prod/main.tf` is the seam. The API's IAM policy,
the Lambda's env var and the `/studio/prod/media-bucket` SSM parameter all
follow it, so step 3 was one line to move and is one line to revert — and the
revert needs no data movement, because the archive still holds everything.

The copy was verified before the seam moved: 938 keys, 1,261,751,658 bytes,
every key present, every size equal, every ETag equal. `aws s3 sync` skips
zero-byte keys ending in `/`, so one folder marker was copied separately; and
it uses multipart copy above 8 MB, which produces a `-N` ETag that cannot be
compared with a single-part MD5, so those 29 objects were re-copied single-part
to make the comparison exact rather than assumed.

The `XHARNESS_S3_*` environment variables became `STUDIO_S3_*` in the same
commit. That is not tidiness: `dev-setup.sh` writes the variable only when it is
absent, so an existing `.env` would have kept a pinned `XHARNESS_S3_BUCKET`
pointing at the archive and quietly kept writing there. Renaming the variable
makes a stale line inert instead of wrong.

### The archive is permanent

`xharness-prod-media-us-east-1` is **not** deleted at the end. It is not a
staging artefact.

Copying current objects moves 959 of 1,677 keys. The other 718 are deleted
objects still recoverable behind a delete marker, and the 1,613 noncurrent
versions are the prior revisions that make an overwrite recoverable. None of it
survives a copy, and none of it is reproducible from anywhere else — it *is* the
recovery history that versioning on this bucket exists to provide.

So the archive keeps `prevent_destroy`, keeps its versioning, and stays in
state. Recovering something from before the cutover means reaching into it. If
it is ever retired, that is a separate deliberate decision with its own
argument, not a tidy-up at the end of this one.

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
