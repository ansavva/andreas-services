# Claude Instructions – studio

## What this service does

Studio is a private media browser for the **x-harness** AI generation pipeline,
served from two hostnames:

| Surface | URL | What it is |
|---|---|---|
| App | `studio.andreas.services` | Vite + React SPA on S3 + CloudFront. Dark-only. |
| API | `studio-api.andreas.services` | Flask Lambda behind an API Gateway custom domain. |

The x-harness pipeline writes every image and video it produces into
`s3://xharness-prod-media-us-east-1/media/`. Studio makes that browsable:
folders keep their structure, images and video are the focus, and every item can
be opened fullscreen or flipped through as a vertical reel.

**Studio reads the library and tidies it — it does not produce it.** It browses,
and it can rename, delete and create folders. It cannot upload, and it cannot
generate: making media is x-harness's job. That is a narrower boundary than the
one this file used to describe ("a reader and only a reader"), and the reasoning
behind the change is in **The media bucket is not ours** below.

## Stack

| Layer | Choice |
|---|---|
| Backend | Flask (Python 3.11) + Mangum, Docker container Lambda behind API Gateway REST |
| Frontend | Vite + React 19 + Tailwind v4 + the design system's **web** leaves, static build to S3 + CloudFront |
| Auth | AWS Cognito (admin-create-only user pool); SRP via Amplify Auth on the SPA, Cognito authorizer on every `/api` route |
| Data | **None.** No DynamoDB, no cache. Listings come straight from S3 on each request. |
| Routing | Path-based, and the path *is* the S3 key. `/media/fred/runs/…/clip.mp4` opens that clip. |
| Media | Presigned S3 GET URLs, direct from the browser to S3 |
| Infra | Terraform in `studio/infra/` (`modules/` + `envs/prod`) |

## Directory Structure

```
studio/
├── backend/                  # Flask + Dockerfile, shipped as a container Lambda
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── studio_core/          # routes → services → clients
│   │   ├── routes/           # browse.py (reads) + manage.py (writes)
│   │   └── services/         # browse.py, manage.py, keys.py
│   └── tests/                # pytest + moto over a miniature of the real bucket
├── frontend/                 # Vite + React SPA (studio.andreas.services)
│   ├── index.html            # pins data-theme="dark"
│   └── src/                  # apis, components, pages, hooks, context, utils, types
├── infra/
│   ├── modules/              # auth, compute, api_gateway, api_domain, hosting
│   └── envs/prod/
├── scripts/                  # create-user.sh, dev-up.sh
└── CLAUDE.md                 # ← this file
```

## The media bucket is not ours

`xharness-prod-media-us-east-1` belongs to the x-harness pipeline. Studio's
Terraform **references it by name and nothing more** — there is deliberately no
`aws_s3_bucket` resource and no `aws_s3_bucket` data source for it in
`studio/infra`. A data source would be harmless today but would put the bucket
one careless refactor away from being managed by this state.

The Lambda role's policy (`modules/compute`) now grants four actions, all
confined to `media/*`: `s3:ListBucket` (prefix-conditioned), `s3:GetObject`,
`s3:PutObject` and `s3:DeleteObject`.

**That is a reversal of what this file used to say, and it was deliberate.** The
old rule was "do not add a write action; a feature that needs one belongs in
x-harness". It changed because tidying is not a pipeline activity — you notice a
run produced nothing worth keeping while you are looking at it, and routing that
back through x-harness meant it never happened. So renaming, deleting and
creating folders live here now.

The parts of the old rule that still hold, and should keep holding:

- **Scope did not widen.** Every grant, read and write alike, stops at
  `media/*`, and `ListBucket` is still prefix-conditioned.
- **`services/keys.py` is still the gate.** IAM is the second line of defence,
  not the first, and `clean_name` refuses a slash rather than escaping it — a
  rename must not be able to become a move.
- **No upload, and no multipart grant.** The only `PutObject` this service makes
  writes a zero-byte folder marker. A real upload would need CORS on a bucket we
  do not own *and* would blow the Lambda's 6 MB request limit on any video, so
  it is blocked by more than policy. Argue for it separately if it is ever
  wanted; do not let it arrive as a side effect of something else.
- **`s3:DeleteObjectVersion` is deliberately absent**, so if the bucket is ever
  versioned this role can only write tombstones, not erase history.

There is an older mirror of the same content at `xharness-assets`. Point
`media_bucket_name` at it if you ever need to; nothing else changes.

## What the bucket looks like

```
media/
├── <subject>/                 # fred, mr-p
│   ├── profile.md
│   ├── originals/             # source photos (.webp, .jpg, .jpeg, .JPG)
│   ├── input/                 # prepped inputs (.png, .jpg)
│   ├── reference/             # reference images + .txt captions
│   └── runs/<ts>_<slug>/      # request.json, result.json, sometimes prompt.json
│       └── output/            # the generated .jpeg / .webp / .mp4
└── misc/runs/<ts>_<slug>/     # unattributed runs, mostly seedance/kling video
```

Three things about this shape drive the UI: run folders sort chronologically
because their names start with a timestamp, a run's output lives one level down
in `output/` so a run folder itself usually shows only JSON, and **a folder has
no LastModified** — a delimited listing returns common prefixes, not objects. The
date sorts therefore fall back to the folder's name, which for a run folder *is*
its date. Do not "fix" that by HEADing every prefix to invent a timestamp.

**The run JSON is deliberately not parsed.** x-harness owns its shape and
changes it freely, so studio serves those files as text and the frontend shows
them read-only. Do not start decoding `request.json` into typed UI — the moment
the pipeline adds a field, a parser becomes a liar.

## Conventions & gotchas

- **The API takes the ID token, never the access token.** A REST
  `COGNITO_USER_POOLS` authorizer only reads the incoming token as an *access*
  token when the method declares `authorization_scopes`. This one declares none
  — and cannot usefully, since the pool has no resource server and Amplify's SRP
  flow mints only `aws.cognito.signin.user.admin` — so it validates an
  *identity* token. Send `session.tokens.idToken` (`apis/client.ts`). The
  failure mode is the confusing one: sign-in succeeds, the app renders, and
  every `/api` call 401s.
- **An authorizer rejection carries no CORS headers unless you add them.** It is
  generated before the integration runs, so Flask's `CORS(...)` never sees it
  and the MOCK preflight only covers the OPTIONS. `modules/api_gateway` sets
  `aws_api_gateway_gateway_response` for `UNAUTHORIZED` and `ACCESS_DENIED`;
  without them a 401 surfaces in the SPA as an opaque CORS failure with no
  status to act on. Both are in the deployment trigger — a gateway response
  needs a redeploy to take effect.
- **Presigned URLs die with the Lambda's credentials, not with `ExpiresIn`.** A
  URL signed by temporary credentials stops working when those rotate, whatever
  expiry was requested. `STUDIO_PRESIGN_TTL_SECONDS` defaults to 900 and the
  frontend re-signs through `/api/asset` from a media element's `onError`
  (`useSignedSrc`), capped at one retry per key.
- **A cross-origin `<a download>` is ignored by browsers.** Downloads work only
  because `/api/asset?disposition=attachment` signs
  `response-content-disposition` into the URL itself.
- **Text is served through `/api/text`, not fetched from the presigned URL.** A
  cross-origin `fetch` to S3 would need a CORS configuration on a bucket studio
  does not own and must not modify.
- **Every card, row and tile is itself a `<button>`, so a second control cannot
  go inside one.** A button nested in a button is invalid HTML that browsers
  resolve by dropping one of them, and which one they drop is not something to
  rely on — and the design system's `Checkbox.Root` is a `role="checkbox"`
  button, so it counts. `CopyKeyButton` and the tile's checkbox are therefore
  always *siblings* of the opening button, positioned over it (`MediaTile`) or
  beside it (`FileRow`, `FolderCard`) — which is why those three carry their
  frame on a wrapper `<div>` rather than on the button. Anything else that
  lands in a listing has to be built the same way. Its feedback is inline for
  the same reason the viewer's is: `ViewerChrome` is often inside a fullscreen
  element, and a toast portalled to `<body>` is not painted while one is.
- **The media grid has a selection mode, and it changes what a press means.**
  Once anything is selected (`useSelection`), pressing a tile extends the
  selection instead of opening it — the photo-library bargain, and the only way
  to pick forty tiles on a touch screen without hunting forty checkboxes. Escape
  clears, but only when no overlay is open, because the reel and the code viewer
  each bind Escape to their own close. Selection is keyed by object key rather
  than by grid index: a listing can be re-fetched underneath one — every write
  does exactly that — and an index-keyed selection would quietly come to mean
  different files.
- **The URL is the S3 key, and CloudFront has to be in on it.** `utils/location`
  maps `media/fred/runs/x/output/clip.mp4` ⟷ `/media/fred/runs/x/output/clip.mp4`,
  segment-encoded so spaces and `#` in real filenames survive; a trailing slash
  means a folder, exactly as it does in S3. The catch is that a share link
  *ends in `.mp4`*, so the viewer-request function in `modules/hosting` routes by
  **location** (`/assets/…` and `/index.html` pass through, everything else
  rewrites) rather than by "does this look like a file". The old
  extension-matching version sent every share link to S3, where the 403/404
  fallbacks rescued it into `index.html` — it worked, by accident, one wasted
  origin round trip at a time.
- **Unmuting has to happen inside the click, not in an effect afterwards.**
  `useReelPlayback.toggleMuted` sets `video.muted` on the element synchronously
  and lets React state follow; the state does not cause the change. A passive
  effect is a later task, and Safari grants sound only within the gesture's own
  turn of the event loop — deferring it is why the unmute button used to do
  nothing. A refused `play()` is caught, not swallowed: playback falls back to
  muted and `blocked` is raised so the UI can say why. Check `volume` too, since
  a muted element sitting at `volume === 0` is still silent after unmuting.
- **The reel is the only viewer.** There was a lightbox beside it — a horizontal
  filmstrip with its own keyboard map and swipe handling — and it is gone.
  Because there is only one viewer now, the axes are free to be specific:
  Up/Down move between items, Left/Right move through *time*. `useKeyboardNav`
  ignores anything targeting an INPUT, which is what lets the scrub bar be a
  native `<input type="range">` and answer the arrow keys itself with no
  coordination between the two.
- **The reel's cursor is an offset, not an S3 continuation token.** Sorting by
  date means the whole subtree must be listed before any page can be cut from it,
  so `browse.reel_items` walks (bounded by `STUDIO_MAX_WALK_OBJECTS`), sorts, and
  presigns *only* the window it returns — which is strictly less signing than the
  old key-order paging did.
- **Every write re-fetches the listing rather than patching state.** A rename
  changes an item's position under `newest` and certainly under `name`; replaying
  that into a sorted array correctly is more code than one request, and it is
  code that would be wrong exactly where nobody tests. The one exception is the
  recursive reel, which drops the item locally (`useReel.dropItem`) because
  re-walking would shift every already-loaded page under the scroll position.
- **Destructive confirmation is in the button, never in a dialog.**
  `ConfirmDeleteButton` arms on the first press, names what it will destroy, and
  disarms on a timeout, on blur, or on Escape. A portalled dialog is not painted
  while a `<video>` is in native fullscreen — the same constraint that keeps
  `CopyKeyButton`'s feedback inline — and a dialog in a fixed position trains a
  second click that lands before anyone reads it.
- **`services/keys.py` is the only thing between a query string and
  `GetObject`.** Every prefix and key is normalised and confined to
  `media/`. Test changes to it directly — `posixpath.normpath` strips a trailing
  slash, which is why the folder check happens on the raw value.
- **Dark-only, and the palette is declared twice.** `src/styles/app.css` sets it
  in `@theme` *and* under `[data-theme='dark']`; `index.html` pins the attribute
  and nothing toggles it. The duplication stops a component that reads a role
  outside the selector from flashing the design system's light default over a
  photograph. Never hard-code a colour at a call site.
- **The design system's leaf resolution is load-bearing and fails silently.**
  `vite.config.ts` puts the `.web.*` forms first in `resolve.extensions` **and**
  in `optimizeDeps.rollupOptions.resolve.extensions`; `tsconfig.json` mirrors it
  as `moduleSuffixes`. `studio-pr.yml` audits the built source map in both
  directions, because picking the wrong leaf compiles cleanly.
- **`@ansavva/design-system` is pinned exactly (0.14.1).** `0.x` caret ranges do
  not pick up minors. Read the package's `CHANGELOG.md` before bumping.
- **React 19**, matching `website/frontend` and `humbugg/marketing`. The design
  system's source uses React 19 DOM props (`inert`, `onScrollEnd`), so React 18
  types fail `tsc` inside `node_modules`.
- **Reel mode mounts a window, not the world.** Only panes within ±2 of the
  snapped index render a media element; the rest keep their height so scroll
  position stays honest. A hundred live `<video>` elements exhausts the decoder.
  Ref callbacks are memoised per key in `useReelPlayback.register` — an inline
  arrow in the render loop is a new identity every render, which would detach and
  re-attach every mounted pane's ref on every tick of the scrub bar.
- **Ties in a date sort are the common case, not the edge.** S3's LastModified
  has one-second resolution and a run writes its whole output inside one second,
  so `_sort_files` breaks ties on the full key, always ascending — two passes
  over a stable sort rather than one `reverse=True` over a composite key, which
  would hand back `frame_9, frame_8, frame_7` for every run. Breaking on the
  *basename* would interleave `originals/`, `reference/` and `runs/` in the
  recursive reel; the key keeps a subject's folders whole.
- Lambda uses `lifecycle { ignore_changes = [image_uri, environment] }`; the
  deploy workflow owns the image tag and the env vars.

## API

Every route is behind the Cognito authorizer except `GET /api/health`.

| Route | Returns |
|---|---|
| `GET /api/health` | `{"status": "ok"}` — liveness, touches no S3 |
| `GET /api/tree?prefix=&sort=` | One delimited listing: `folders`, `files` (each presigned), `breadcrumbs`, `counts` |
| `GET /api/reel?prefix=&cursor=&page_size=&sort=` | Images and video beneath a prefix, recursively, paginated |
| `GET /api/asset?key=&disposition=` | A fresh presigned URL for one object |
| `GET /api/text?key=` | A `.json` / `.md` / `.txt` object's contents, capped at 1 MB |
| `POST /api/folder` | `{prefix, name}` → creates an empty folder. 409 if taken |
| `PATCH /api/object` | `{key, name}` → renames one object in place. 409 if taken |
| `PATCH /api/folder` | `{prefix, name}` → renames a folder and its subtree |
| `DELETE /api/objects` | `{keys: [...]}` → deletes 1..N objects |
| `DELETE /api/folder` | `{prefix}` → deletes a folder and its subtree |

`sort` is one of `newest` (default), `oldest`, `name`, `name_desc`.

The write routes carry a JSON body, `DELETE /api/objects` included. That is
unusual but well-defined, and API Gateway's Lambda proxy passes it through
intact; the alternative for a grid selection is a few hundred repeated `?key=`
parameters, which is a URL length limit waiting to happen on exactly the case
bulk delete exists for.

**Four places have to agree on the allowed methods**, because a browser's
preflight is answered by API Gateway rather than by Flask: `CORS(methods=...)` in
`app_factory.py`, the MOCK integration response in `modules/api_gateway`, and the
`UNAUTHORIZED` and `ACCESS_DENIED` gateway responses beside it. A verb missing
from any of them is a CORS failure no Flask configuration can rescue.

### Limits

| Env var | Default | Guards |
|---|---|---|
| `STUDIO_MAX_BULK_KEYS` | 1000 | One `DeleteObjects` round trip |
| `STUDIO_MAX_FOLDER_OBJECTS` | 2000 | A folder rename/delete the Lambda can finish |
| `STUDIO_MAX_WALK_OBJECTS` | 20000 | The recursive reel's walk |

The folder cap is a **refusal**, not a truncation: a rename that stopped halfway
would leave the same objects under two prefixes with no record of which half
moved. Renames copy before they delete, in that order and never the reverse — a
failed delete leaves a duplicate, which is visible and fixable, while the reverse
order would lose data.

## Local development

```bash
# Both surfaces together (backend :8000, frontend :5173).
aws login
./studio/scripts/dev-up.sh
```

Or separately:

```bash
cd studio/backend
poetry install --no-root
eval "$(aws configure export-credentials --format env)"   # boto3 needs real env creds
poetry run python -m studio_core.handlers.local.api.api_dev_server
poetry run pytest                                          # moto-backed, no AWS needed

cd studio/frontend
export NODE_AUTH_TOKEN=$(gh auth token)                    # needs read:packages
npm ci && npm run dev
```

`aws login` writes a cache only the AWS CLI reads, so `aws sts
get-caller-identity` succeeding tells you nothing about whether boto3 can see
credentials — export them. Same split the root `CLAUDE.md` documents for
Terraform's provider.

Copy `frontend/.env.local.example → .env.local` and fill in the Cognito ids from
the prod outputs, or the app shows "Auth is not configured".

## Creating users

There is no sign-up. Accounts are created out of band:

```bash
STUDIO_EMAIL=you@example.com ./studio/scripts/create-user.sh
```

Cognito emails a temporary password; signing in with it prompts for a new one.
Pass `STUDIO_PASSWORD` to set a permanent one directly instead.

## Deployment

`.github/workflows/studio-prod.yaml` — `detect-changes → bootstrap-ecr →
build-and-push → deploy-infra → update-lambda + deploy-frontend`. The SPA is
built in `deploy-frontend` rather than earlier because Vite inlines every
`VITE_*` value at build time and the Cognito ids come out of the apply.

Terraform state: `s3://andreas-services-terraform-state/studio/prod/terraform.tfstate`.
