# Studio

An AI media generation pipeline, and a private browser over what it produces.

| Surface | URL |
|---|---|
| App | https://studio.andreas.services |
| API | https://studio-api.andreas.services |

Studio is two things sharing one library:

- **The pipeline** — a set of Claude Code skills and one `studio` CLI that
  generate images and video through Replicate. It runs on your own machine,
  inside Claude, and never deploys. See [`docs/PIPELINE.md`](docs/PIPELINE.md).
- **The app** — the web browser over the results, at the two URLs above. See
  [`docs/WEB_APP.md`](docs/WEB_APP.md). The rest of this file is about it.

The library is the **catalog** — a DynamoDB table holding characters, projects,
runs, scenes and movies as rows with UUIDs, plus the folder tree that hangs off
them — with the bytes in an S3 bucket behind it. Every entity's root folder and
every S3 key is named by id, never by name, so a rename changes one row. The
deployed app reads `studio-prod-catalog` and `s3://studio-prod-media-us-east-1/`;
local work runs against this machine's dev stack.

## What it does

- **Entity pages, addressed by id.** `/c/<id>` is a character (profile,
  references, its folders and files), `/p/<id>` a project (overview, runs,
  scenes, movies, inputs, files), `/p/<id>/r/<run_id>` one run — its envelope,
  outputs and payloads — `/s/<id>` a scene, `/m/<id>` a movie. `/characters`,
  `/projects` and `/templates` are the lists. Home shows characters, projects
  and the most recent media; a recent tile opens a feed of everything beneath it.
- **Browse** the folder tree at `/f` (the library root) or `/f/<id>`, newest
  first; the order is switchable and travels in the URL as `?sort=`. The grid
  shows every image and video in a folder; videos paint their own first frame
  as a poster and show their duration.
- **One file, open**, at `/o/<id>`: an ordinary page with one player, the file's
  details beside it, and a filmstrip of its neighbours underneath. `?in=` names
  the feed the neighbours come from; without it the file shows on its own with a
  link to whatever owns it. A video gets a transport — back 5, play/pause,
  forward 5, a seek bar and the two times.
- **Share links** name a node by id, so a link survives every rename and move.
- **A page per text file** — the pipeline's `request.json`, `result.json`,
  `prompt.json` and `scene.json`, the character profiles and the reference
  captions. JSON is pretty-printed, markdown is rendered, and every one **can be
  edited and saved** as its literal bytes. Leaving with unsaved changes asks
  first. A file too large to be shown in full cannot be edited, because saving a
  truncated copy would delete the rest of it.
- **Tidy up.** Create a folder, rename, move **or copy** files and folders
  anywhere in the library through one destination picker, delete one file, a
  whole folder, or a grid selection. A copy into a folder that already holds the
  name is numbered (`clip (2).mp4`), never overwritten or skipped.
- **Upload.** The folder toolbar takes any number of files into the folder on
  screen, numbered the same way if a name is taken. The bytes go **straight to
  S3** on a signed PUT (`POST /api/nodes/<id>/upload-url`, then
  `POST /api/nodes/<id>/confirm-upload`), so the Lambda's 6 MB request limit
  never applies. HEIC is refused with a message: no browser but Safari draws it.
- **Plan, approve and submit runs** from a run page, through the same API the
  CLI uses. The payload is shown in full before the yes, and
  `POST /api/runs/<id>/submit` refuses a run whose plan has changed since it was
  approved — hard rule #2 in `CLAUDE.md`.
- **Switch library.** An account can be a member of more than one, and a subtree
  can be handed from one to another (`POST /api/nodes/<id>/transfer`, owner in
  both).
- **Download** any single file (`GET /api/nodes/<id>/download-url`).

### Keys

On the open-file page. Nothing fires while a text box or the seek bar has focus.

| Key | Does |
|---|---|
| ← / → | Previous / next file (the seek bar scrubs with them when it is focused) |
| `space` | Play / pause |
| `m` | Mute / unmute |
| `f` | Fullscreen |
| `Esc` | Close — back to wherever the file was opened from |

## What bounds it

The Lambda's IAM role carries `s3:PutObject` and `s3:DeleteObject` alongside the
read grants, over the whole bucket. Every key is validated before it reaches S3,
the library root cannot be renamed or deleted, and folder operations refuse a
subtree larger than `STUDIO_MAX_FOLDER_OBJECTS` rather than doing half of one.
The bucket is versioned and the role holds no `s3:DeleteObjectVersion`, so every
delete is a recoverable tombstone.

An upload is bounded by its signature rather than by IAM: one key the caller does
not name, one exact content length, one content type, and a TTL
(`STUDIO_UPLOAD_TTL_SECONDS`) shorter than a read URL's. There is no multipart
grant, so `STUDIO_MAX_UPLOAD_BYTES` is S3's single-PUT ceiling. The bucket's CORS
rule allows `PUT` only, and `backend/tests/unit/test_cors_agreement.py` holds
both media buckets to it. Saving a text file is not an upload:
`PATCH /api/nodes/<id>/text` refuses any node that is not already a file
carrying bytes. **Not a social app** — no comments, no counts, no cross-library
feed.

## Access

Sign-in is required and there is no sign-up. The Cognito pool is
admin-create-only, and an account on its own reaches nothing: what a caller can
see is the libraries they are a member of, and membership is granted out of band.

```bash
STUDIO_EMAIL=you@example.com ./studio/scripts/create-user.sh
STUDIO_EMAIL=you@example.com STUDIO_LIBRARY=lib-… ./studio/scripts/add-member.sh
STUDIO_LIBRARY=lib-… ./studio/scripts/add-member.sh --list
```

**No API route grants membership, deliberately** — one could grant itself access
to somebody else's library. `STUDIO_ROLE` is `member` by default; `owner` is the
wider grant and the one a transfer between libraries requires in both.

## Development

A per-machine dev stack comes first; `dev-up.sh` refuses to start without one.

```bash
aws sts get-caller-identity                          # confirm the access key resolves
./studio/scripts/dev-aws-setup.sh                    # once per machine
./studio/scripts/dev-user.sh --generate-password     # its one test account
./studio/scripts/dev-setup.sh                        # the pipeline — installs uv, syncs the dev profile
./studio/scripts/dev-up.sh                           # the app — backend :8000, frontend :5173
```

[`CLAUDE.md`](./CLAUDE.md) is the index over both halves and holds the hard
rules; [`docs/WEB_APP.md`](docs/WEB_APP.md) the app's architecture and API
surface; [`docs/PIPELINE.md`](docs/PIPELINE.md) the skills and the entity trees;
[`infra/README.md`](infra/README.md) the bucket and the Terraform.
