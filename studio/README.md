# Studio

A private media browser for the **x-harness** AI generation pipeline.

| Surface | URL |
|---|---|
| App | https://studio.andreas.services |
| API | https://studio-api.andreas.services |

x-harness writes every image and video it generates into
`s3://xharness-prod-media-us-east-1/media/`, organised by subject and by run.
Studio makes that library viewable: the folder structure is preserved so a
subject's originals, references and runs stay where you expect them, while the
images and video themselves get the space.

## What it does

- **Browse** the bucket's folders, with run folders shown as a name and a date
  rather than one long timestamped token.
- **Grid** of every image and video in a folder. Videos paint their own first
  frame as a poster and show their duration.
- **Fullscreen lightbox** — arrow keys, swipe, `f` for fullscreen, `space` to
  play or pause, `Esc` to close.
- **Reel** — a vertical, one-per-screen scroll through every image and video
  beneath the current folder, recursively. Exactly one video plays at a time and
  everything starts muted.
- **Read-only file viewer** for the pipeline's `request.json`, `result.json`,
  `prompt.json`, the subject `profile.md` files and the reference captions. JSON
  is pretty-printed, markdown is rendered, nothing is editable.
- **Download** any single file.

## What it deliberately does not do

It does not generate, edit, upload, rename or delete anything. The Lambda's IAM
role holds `s3:ListBucket` and `s3:GetObject` and nothing else, so studio
*cannot* write to the x-harness bucket even by accident.

It is also not a social app: no likes, no comments, no sharing, no cross-folder
infinite feed. The reel is a way to flip through a folder quickly, and that is
all it is.

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
