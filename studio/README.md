# Studio

An AI media generation pipeline, and a private browser over what it produces.

| Surface | URL |
|---|---|
| App | https://studio.andreas.services |
| API | https://studio-api.andreas.services |

Studio is two things sharing one library:

- **The pipeline** — a set of Claude Code skills that generate images and video
  through Replicate. It runs on your own machine, inside Claude, and never
  deploys anywhere. See [`docs/PIPELINE.md`](docs/PIPELINE.md).
- **The app** — the web browser over the results, at the two URLs above. See
  [`docs/WEB_APP.md`](docs/WEB_APP.md).

The rest of this file is about the app; the pipeline's own doc covers the other
half.

The pipeline records every image and video it generates in the **catalog** — a
DynamoDB table that holds every folder, name, parent and timestamp — with the
bytes in an S3 bucket behind it. The tree is split between `characters/` (who a
subject is — seeds, references, a profile) and `projects/` (what was generated
of them — runs and scenes). Studio makes that library viewable: the folder
structure is preserved so a subject's seeds, references and runs stay where you
expect them, while the images and video themselves get the space.

Which stack that is depends on where you are: the deployed app reads
`studio-prod-catalog` and `s3://studio-prod-media-us-east-1/`, while local work
runs against this machine's dev stack. This paragraph named the prod bucket
alone until August 2026, when both of those stopped being true at once.

## What it does

- **Browse** the library's folders, newest first, with run folders shown as a name
  and a date rather than one long timestamped token. The order is switchable —
  newest, oldest, or by name either way — and travels in the URL.
- **Grid** of every image and video in a folder. Videos paint their own first
  frame as a poster and show their duration.
- **Reel** — the one media viewer. A vertical, one-per-screen scroll; opening a
  tile opens the reel on that tile, and *Play reel* walks everything beneath the
  current folder recursively. Exactly one video plays at a time, starting muted.
  Videos get a transport along the bottom — play/pause, a seek bar, skip either
  way — while sound sits in the top bar with the other controls, because the
  bottom edge of a phone screen is where the browser puts its own toolbar.
- **Share links.** The URL names a node by **id** — `/f/<id>` is a folder,
  `/o/<id>` is one open file — so a link survives the rename or move that used to
  break it. It used to *be* the S3 path
  (`/projects/<project>/runs/2026-08-14_…/output/clip.mp4`); those links still
  work, resolved once through `GET /api/resolve` and replaced with the id URL.
- **A page per text file** — the pipeline's `request.json`, `result.json`,
  `prompt.json` and `scene.json`, the subject `profile.yaml` files and the
  reference captions. JSON is pretty-printed and markdown is rendered, and every
  one of them **can be edited and saved**: press Edit, get the file's literal
  bytes in a textarea, Save writes it back. Leaving with unsaved changes asks
  first. A file too large to be shown in full cannot be edited, because saving a
  truncated copy would delete the rest of it.
- **Tidy up.** Create a folder, rename a file or a folder, move **or copy** files
  and folders anywhere in the library, delete one file, a whole folder, or a grid
  selection. Move and copy share one picker you browse to a
  destination in — a folder cannot be moved inside itself, and the picker greys
  that branch out rather than letting the request come back refused. A copy into a
  folder that already holds the name is numbered (`clip (2).mp4`), never
  overwritten or skipped. Delete confirms twice in the control itself — press once
  and it turns red and names what it is about to remove, press again and it goes.
  There is no dialog.
- **Upload.** The folder toolbar takes any number of files into the folder on
  screen, numbered the same way a copy is if a name is taken. HEIC is refused with
  a message, because no browser but Safari can draw it.
- **Switch library.** An account can be a member of more than one, and a subtree
  can be handed from one to another (`POST /api/nodes/<id>/transfer`, owner in
  both).
- **Download** any single file.

**There used to be a star, and there is no longer one.** Favouriting copied a
file onto `projects/<project>/favorites/` — a destination studio *derived* from
the file's own key, which meant studio naming folders the pipeline owns. Generic
copy replaced it: you choose the destination, and a copy is always a copy rather
than bookkeeping about whether one had been made already. The old folders are
still there, as ordinary folders.

### Keys

| Key | Does |
|---|---|
| ↑ / ↓ | Previous / next item |
| ← / → | Seek 5s back / forward in a video (previous / next for a still) |
| `space` | Play / pause |
| `m` | Mute / unmute |
| `f` | Fullscreen |
| `Esc` | Close |

## What it deliberately does not do

**It used to be a strict reader, and that changed.** The Lambda's IAM role now
carries `s3:PutObject` and `s3:DeleteObject` alongside the read grants, because
deciding a run produced nothing worth keeping happens while you are looking at
it. All four grants share one scope, and that scope is now the whole bucket —
the pipeline dropped the `media/` prefix they used to be confined to. Everything
else about that boundary is unchanged: every key is validated before it reaches
S3 and the library root itself cannot be renamed or deleted, folder operations
refuse a subtree larger than `STUDIO_MAX_FOLDER_OBJECTS` rather than doing half
of one, and renames and moves copy before they delete so a failure leaves a
duplicate rather than a hole. The bucket is versioned and the role cannot delete
a version, so what it does remove is recoverable.

**Upload arrived, and the sentence it replaced is worth keeping.** This paragraph
read "there is still no upload" on two grounds: routing bytes through the Lambda
caps a file at 6 MB, useless for video, and a direct browser upload would need a
CORS rule on the bucket. Both were answered rather than overruled.
`POST /api/nodes/<id>/upload-url` signs a PUT the browser sends **straight to
S3**, so the 6 MB request limit never applies; and studio owns the bucket now, so
it sets that rule itself — one line, `PUT` only, `content-type` +
`content-length`, no `GET`, and `backend/tests/test_cors_agreement.py` holds both
media buckets to it.

What bounds an upload is the signature rather than the IAM policy: one key the
caller does not name, one exact content length, one content type, and a TTL
shorter than a read URL's. There is still **no multipart grant**, so
`STUDIO_MAX_UPLOAD_BYTES` is S3's single-PUT ceiling and not a policy number.

**Studio still does not generate.** That is the boundary that mattered, and "no
upload" was never the same statement. Making media is the pipeline's job, and the
pipeline decides what to make and pays for it.

Saving a text file is still not an upload either: it refuses any node that is not
a file already carrying bytes, so it can overwrite a `profile.yaml` and cannot
bring a new object into the library. That check is the whole difference and is
deliberately a single, testable line.

**Not a social app.** No comments, no counts, no cross-folder infinite feed. The
reel is a way to flip through a folder quickly, and that is all it is.

## Access

Sign-in is required and there is no sign-up. The Cognito pool is
admin-create-only; accounts are provisioned with:

```bash
STUDIO_EMAIL=you@example.com ./studio/scripts/create-user.sh
```

An account on its own reaches nothing: what a caller can see is the libraries
they are a member of, and membership is granted out of band for the same reason
the account is.

```bash
STUDIO_EMAIL=you@example.com STUDIO_LIBRARY=lib-… ./studio/scripts/add-member.sh
STUDIO_LIBRARY=lib-… ./studio/scripts/add-member.sh --list
```

**There is no API route that grants membership, deliberately** — one would be a
route that could grant itself access to somebody else's library. `STUDIO_ROLE`
is `member` by default; `owner` is the wider grant and the one a transfer
between libraries requires in both.

## Development

**A per-machine dev stack comes first, and `dev-up.sh` refuses to start without
one** — an API with no Cognito pool 500s on every call, so failing early is the
faster way to find out.

```bash
aws sts get-caller-identity                          # confirm the access key resolves
./studio/scripts/dev-aws-setup.sh                    # once per machine
./studio/scripts/dev-user.sh --generate-password     # its one test account
```

```bash
./studio/scripts/dev-up.sh        # the app — backend :8000, frontend :5173
```

```bash
./studio/scripts/dev-setup.sh     # the pipeline — installs uv, warms caches
```

| Doc | What is in it |
|---|---|
| [`CLAUDE.md`](./CLAUDE.md) | The index over both halves, and the hard rules |
| [`docs/WEB_APP.md`](docs/WEB_APP.md) | App architecture, the API surface, the gotchas |
| [`docs/PIPELINE.md`](docs/PIPELINE.md) | The skills, the S3 trees, run/scene/movie |
| [`infra/README.md`](infra/README.md) | The bucket and the Terraform |
