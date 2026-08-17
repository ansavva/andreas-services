# Studio

A private media browser for the **x-harness** AI generation pipeline.

| Surface | URL |
|---|---|
| App | https://studio.andreas.services |
| API | https://studio-api.andreas.services |

x-harness writes every image and video it generates into
`s3://xharness-prod-media-us-east-1/`, split between `characters/` (who a
subject is — seeds, references, a profile) and `projects/` (what was generated
of them — runs and scenes). Studio makes that library viewable: the folder
structure is preserved so a subject's seeds, references and runs stay where you
expect them, while the images and video themselves get the space.

## What it does

- **Browse** the bucket's folders, newest first, with run folders shown as a name
  and a date rather than one long timestamped token. The order is switchable —
  newest, oldest, or by name either way — and travels in the URL.
- **Grid** of every image and video in a folder. Videos paint their own first
  frame as a poster and show their duration.
- **Reel** — the one media viewer. A vertical, one-per-screen scroll; opening a
  tile opens the reel on that tile, and *Play reel* walks everything beneath the
  current folder recursively. Exactly one video plays at a time, starting muted.
  Videos get a transport: play/pause, a seek bar, and skip either way.
- **Share links.** The URL is the S3 path
  (`/projects/fred/runs/2026-08-14_…/output/clip.mp4`), so the address bar is always
  a link to exactly what is on screen.
- **A page per text file** — the pipeline's `request.json`, `result.json`,
  `prompt.json` and `scene.json`, the subject `profile.yaml` files and the
  reference captions. JSON is pretty-printed and markdown is rendered, and every
  one of them **can be edited and saved**: press Edit, get the file's literal
  bytes in a textarea, Save writes it back. Leaving with unsaved changes asks
  first. A file too large to be shown in full cannot be edited, because saving a
  truncated copy would delete the rest of it.
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
x-harness dropped the `media/` prefix they used to be confined to. Everything
else about that boundary is unchanged: every key is validated before it reaches
S3 and the library root itself cannot be renamed or deleted, folder operations
refuse a subtree larger than `STUDIO_MAX_FOLDER_OBJECTS` rather than doing half
of one, and renames and moves copy before they delete so a failure leaves a
duplicate rather than a hole.

**There is still no upload**, and that is a constraint as much as a decision: a
browser upload needs a CORS configuration on a bucket studio does not own and
must not modify, and routing the bytes through the Lambda caps a file at 6 MB —
useless for video. Generating media remains x-harness's job.

Saving a text file is the one write that looks like an upload and is not: it
refuses any key that does not already exist, so it can overwrite a `profile.yaml`
but cannot bring a new object into the library. That check is the whole
difference, and it is deliberately a single, testable line.

It is also not a social app: no likes, no comments, no cross-folder infinite
feed. The reel is a way to flip through a folder quickly, and that is all it is.

## Access

Sign-in is required and there is no sign-up. The Cognito pool is
admin-create-only; accounts are provisioned with:

```bash
STUDIO_EMAIL=you@example.com ./studio/scripts/create-user.sh
```

## Development

```bash
aws login
./studio/scripts/dev-up.sh        # backend :8000, frontend :5173
```

See [`CLAUDE.md`](./CLAUDE.md) for the architecture, the API surface, and the
gotchas worth knowing before changing anything.
