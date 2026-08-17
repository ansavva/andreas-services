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

**`xharness-prod-media-us-east-1`**, `us-east-1`. Around 500 objects and 700 MB
of generated media, and **there is no second copy of it anywhere.**

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

### Why the name is wrong, and why it stays

The convention is `[project]-[env]-[component]-[region]`, which would make this
`studio-prod-media-us-east-1`. It is not, because the bucket was created from a
separate `xharness` repo before studio absorbed the pipeline.

Renaming an S3 bucket is a destroy-and-recreate, so fixing it means copying
~700 MB to a new bucket and re-pointing the skills' default, the backend config
default, the Terraform variable, the deploy workflow and the tests **in one
move**. That is a deliberate separate pass, not a side effect of something else.
Until then the name is grandfathered and the `XHARNESS_S3_*` environment
variables the skills read are grandfathered with it — do not rename one without
the other.

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
s3://xharness-prod-media-us-east-1/
  characters/<name>/          an IDENTITY record
      profile.yaml            the bible, including the described reference index
      reference/              generated character imagery, in purpose subfolders
      corpus/  seed/  archive/
  projects/<project>/         a piece of WORK
      project.json
      runs/  chains/  scenes/  movies/  favorites/  input/
  phrasebook/wording.yaml
```

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
aws s3 presign s3://xharness-prod-media-us-east-1/characters/<name>/reference/face/<name>_1.webp --expires-in 3600
```

```bash
aws s3 cp ./<name>_1.webp s3://xharness-prod-media-us-east-1/characters/<name>/reference/face/<name>_1.webp
```

```bash
aws s3 cp s3://xharness-prod-media-us-east-1/projects/<project>/runs/<run_id>/output/clip.mp4 ./clip.mp4
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
