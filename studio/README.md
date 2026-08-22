# Studio

An AI media generation pipeline, and a private browser over what it produces.

| Surface | URL |
|---|---|
| App | https://studio.andreas.services |
| API | https://studio-api.andreas.services |

Studio is two things sharing one S3 bucket:

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

- **Browse** the bucket's folders, newest first, with run folders shown as a name
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
- **Share links.** The URL is the S3 path
  (`/projects/<project>/runs/2026-08-14_…/output/clip.mp4`), so the address bar is always
  a link to exactly what is on screen.
- **A page per text file** — the pipeline's `request.json`, `result.json`,
  `prompt.json` and `scene.json`, the subject `profile.yaml` files and the
  reference captions. JSON is pretty-printed and markdown is rendered, and every
  one of them **can be edited and saved**: press Edit, get the file's literal
  bytes in a textarea, Save writes it back. Leaving with unsaved changes asks
  first. A file too large to be shown in full cannot be edited, because saving a
  truncated copy would delete the rest of it.
- **Favourite** a photo or a clip and it is copied onto that project's shelf —
  `projects/<project>/favorites/`, flat, alongside the picks that are already there.
  You never say where: the star knows, because the file's own path does. From a
  grid selection it takes the whole selection at once, and a selection spanning
  two subjects splits itself between their projects. A gold star means the file
  really is on the shelf, not that you pressed something — it is read back from
  the bucket, so it is still there tomorrow and on another device. Pressing it
  twice does nothing the second time; two different clips that share a name get
  the second one numbered (`shot-01 (2).mp4`) rather than overwritten. Files in
  `characters/` have no star at all — that tree is who a subject *is*, not
  output to pick between — and neither does the run metadata. To un-favourite,
  delete the copy from inside the favourites folder.
- **Tidy up.** Create a folder, rename a file or a folder, move files and folders
  anywhere in the library, delete one file, a whole folder, or a grid selection.
  Moving opens a picker you browse to a destination in — a folder cannot be moved
  inside itself, and the picker greys that branch out rather than letting the
  request come back refused. Delete confirms twice in the control itself — press
  once and it turns red and names what it is about to remove, press again and it
  goes. There is no dialog.
- **Download** any single file.

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

**There is still no upload.** Routing the bytes through the Lambda caps a file
at 6 MB, which is useless for video, and a direct browser upload would need a
CORS rule on the bucket. Generating media is the pipeline's job, and the
pipeline runs on a laptop under a human's own AWS login rather than through this
API — which is the boundary that actually matters, and the reason this one is
worth keeping even though studio now owns the bucket and could set that CORS
rule if it wanted to.

Two writes look like uploads and are not. Saving a text file refuses any key that
does not already exist, so it can overwrite a `profile.yaml` but cannot bring a
new object into the library — that check is the whole difference, and it is
deliberately a single, testable line. Favouriting *does* add an object, but it is
a server-side copy of something already in the bucket, so the bytes never come
from outside and never travel through the Lambda; a 200 MB clip is favourited as
cheaply as a thumbnail.

**A favourite is a pick, not a like.** It is a file in a folder you can open in
the AWS console, and its whole purpose is to survive studio being switched off.
Beyond that this is not a social app: no comments, no counts, no cross-folder
infinite feed. The reel is a way to flip through a folder quickly, and that is
all it is.

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

```bash
aws login
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
