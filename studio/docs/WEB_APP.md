# studio — the web app

The deployed half of studio: the browser over the media library. For the local
generation pipeline that fills that library, see [PIPELINE.md](PIPELINE.md); for
the map of both, [../CLAUDE.md](../CLAUDE.md).

## What this service does

Studio's app half is a private media browser, served from two hostnames:

| Surface | URL | What it is |
|---|---|---|
| App | `studio.andreas.services` | Vite + React SPA on S3 + CloudFront. Dark-only. |
| API | `studio-api.andreas.services` | Flask Lambda behind an API Gateway custom domain. |

The generation pipeline writes every image and video it produces into
`s3://studio-prod-media-us-east-1/`. Studio makes that browsable:
folders keep their structure, images and video are the focus, and every item can
be opened fullscreen or flipped through as a vertical reel.

**Studio reads the library and tidies it — it does not produce it.** It browses,
and it can rename, move, copy, delete, create folders, and edit the text
files in place. It cannot upload, and it cannot generate: making media is the
pipeline's job, and the pipeline runs locally under a human's own AWS login, not
through this API. That is a narrower boundary than the one this file used to
describe ("a reader and only a reader"), and the reasoning behind the change is
in **What this service may do to the bucket** below.

The line between "edit a text file" and "upload" is worth stating, because it is
thinner than it sounds and is held in exactly one place: `manage.update_text`
refuses a key that does not already exist.

**Copying is the one write that adds an object, and the distinction that keeps
it honest is where the bytes come from.** A copy is a server-side `CopyObject`
of something already in the bucket, so nothing arrives from outside; what studio
still cannot do is put bytes in that were not there already. Every write it accepts either copies, moves, overwrites or removes
something the pipeline produced.

## Stack

| Layer | Choice |
|---|---|
| Backend | Flask (Python 3.11) + Mangum, Docker container Lambda behind API Gateway REST |
| Frontend | Vite + React 19 + Tailwind v4 + the design system's **web** leaves, static build to S3 + CloudFront |
| Auth | AWS Cognito (admin-create-only user pool); SRP via Amplify Auth on the SPA, Cognito authorizer on every `/api` route |
| Data | **None.** No DynamoDB, no cache. Listings come straight from S3 on each request. |
| Routing | Path-based, and the path *is* the S3 key. `/projects/<project>/runs/…/clip.mp4` opens that clip. |
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
│   ├── modules/              # auth, compute, api_gateway, api_domain, hosting, media
│   └── envs/prod/
├── scripts/                  # create-user.sh, dev-up.sh, dev-setup.sh
├── .claude/skills/           # the generation pipeline — local only, never deploys
├── docs/
│   ├── PIPELINE.md           # the local half
│   └── WEB_APP.md            # ← this file
└── CLAUDE.md                 # the index over both
```

## What this service may do to the bucket

`studio-prod-media-us-east-1` is studio's own bucket, declared in
`infra/modules/media` and imported into `studio/prod` state in August 2026. It
did not used to be: it was provisioned from a separate repo, and this section
used to be titled *The media bucket is not ours* and forbade any resource or
data source for it. That is no longer the arrangement — see
[../infra/README.md](../infra/README.md).

What did **not** change is which side of the fence this API sits on. The
pipeline writes to the bucket from a laptop under a human's own AWS login. This
Lambda is the only thing reachable from the internet, so it is still the thing
worth scoping, and everything below still applies to it.

The Lambda role's policy (`modules/compute`) now grants four actions:
`s3:ListBucket` (prefix-conditioned), `s3:GetObject`, `s3:PutObject` and
`s3:DeleteObject`. All four are scoped to `media_root_prefix`, **which is now
empty** — see *What the bucket looks like* below — so in practice they cover the
whole bucket.

**That is a reversal of what this file used to say, and it was deliberate.** The
old rule was "do not add a write action; a feature that needs one belongs in the
pipeline". It changed because tidying is not a pipeline activity — you notice a
run produced nothing worth keeping while you are looking at it, and routing that
back through the pipeline meant it never happened. So renaming, deleting and
creating folders live here now.

The parts of the old rule that still hold, and should keep holding:

- **`services/keys.py` is the gate.** `clean_name` refuses a slash rather than
  escaping it — a rename must not be able to become a move — and
  `assert_inside_root` refuses an operation aimed at the root, so "delete the
  library" is not expressible through the API. This used to be described as the
  first of two lines of defence with IAM behind it; with the prefix empty it is
  the only one, which is the reason to be conservative when changing it.
- **No upload, and no multipart grant.** The `PutObject` calls this service
  makes write a zero-byte folder marker and overwrite an *existing* text file
  (`manage.update_text`, capped at `max_text_bytes` and refused outright for a
  key that is not already there, so it cannot create); `CopyObject` supplies the
  rest. A real upload would need CORS on the bucket *and* would blow the
  Lambda's 6 MB request limit on any video, so it is blocked by more than
  policy. (Studio can set that CORS rule now that it owns the bucket, which
  removes one of the two obstacles — but not the interesting one.) Argue for it separately if it is ever
  wanted; do not let it arrive as a side effect of something else.
- **`copy_objects` keeps its source, and it is the only write that does.** Every
  other `CopyObject` here is the first half of a rename or a move and is
  followed by a delete, which makes this the only write that *adds* an object
  rather than relocating one — see the correction at the top of this file. The
  bytes still come from inside the bucket, so "studio cannot upload" is
  untouched by it.
- **`s3:DeleteObjectVersion` is deliberately absent**, and the bucket **is**
  versioned (`infra/modules/media`), so this role can only write tombstones, not
  erase history. Every delete it can perform is recoverable. With the prefix
  confining nothing, this is the strongest guarantee left standing — do not
  drop it to tidy the policy.

The part that **did** change and should not be glossed over: scope. It used to
be true that every grant stopped at `media/*`. With `media_root_prefix` empty
that sentence is no longer true of either half — a write-capable role now reaches
the whole bucket. Setting the prefix to a real value narrows reads and writes
together, and is the lever to reach for if that ever needs to be true again.

There is **no second copy of this bucket anywhere.** An older mirror called
`xharness-assets` used to exist and this file used to offer it as a fallback;
it has since been deleted, and the note is removed rather than left to be
believed. Versioning and `prevent_destroy` are what stand in its place.

`xharness-prod-media-us-east-1`, the bucket this one was renamed out of, is not
a fallback either: it was deleted in August 2026 once the copy was verified, and
its version history went with it. Nothing stands behind this bucket now.

## What the bucket looks like

**There is no `media/` wrapper.** There was until August 2026, and studio's
browsable root was hard-coded to it in five places — the Flask config default,
the SPA's `ROOT_PREFIX`, the Terraform variable, the IAM prefix condition and
the deploy workflow's `jq` block. When the pipeline flattened the bucket, every
listing came back empty and the app rendered an empty root with no error, since
a prefix that matches nothing is not an error to S3. The browsable root is now
the bucket itself (`media_root_prefix = ""`).

```
characters/<subject>/           # who a subject is
├── profile.yaml
├── seed/                       # source photos (.webp, .jpg, .jpeg, .JPG, .heic)
├── corpus/                     # the wider photo set
├── reference/                  # reference images + .txt captions,
│   └── <face|body|frame|wardrobe>/   #   sometimes split by category
└── archive/                    # superseded output kept around
projects/<subject>/             # what was generated of them
├── runs/<ts>_<slug>/           # request.json, result.json, sometimes prompt.json
│   └── output/                 # the generated .jpeg / .webp / .mp4
├── scenes/<ts>_<slug>/         # scene.json + shots/ + output/, a stitched sequence
├── chains/<name>.json          # a scene's shot-to-shot plan
└── favorites/                  # an ordinary folder someone made, from before
                               # copying let you choose a destination
projects/misc/runs/<ts>_<slug>/ # unattributed runs, mostly seedance/kling video
phrasebook/wording.yaml         # shared prompt wording
```

Four things about this shape drive the UI: run and scene folders sort
chronologically because their names start with a timestamp; a run's output lives
one level down in `output/`, so a run folder itself usually shows only JSON; a
subject is split across two top-level trees — `characters/<name>/` and
`projects/<name>/` are the same subject, and reel mode is what puts them back
together, since it walks recursively from wherever you are; and **a folder has
no LastModified** — a delimited listing returns common prefixes, not objects. The
date sorts therefore fall back to the folder's name, which for a run folder *is*
its date. Do not "fix" that by HEADing every prefix to invent a timestamp.

The pipeline owns this layout and has reshaped it before. When it changes again,
`media_root_prefix` is the first knob that matters, and it is now the only one.

There were briefly two more — `STUDIO_PROJECTS_PREFIX` and
`STUDIO_FAVORITES_FOLDER` — because favouriting had to *derive* a destination
from a key, which meant studio naming folders the pipeline owns. Deleting that
feature deleted the need: a copy is handed its destination, so studio no longer
knows what a "project" is or which folder inside one is special. **Nothing else
in studio names a folder, and nothing else should start to.**

**The run JSON is deliberately not parsed.** The pipeline owns its shape and
changes it freely, so studio serves those files as text and the frontend shows
them as text. Do not start decoding `request.json` into typed UI — the moment
the pipeline adds a field, a parser becomes a liar.

That holds even though those files are now **editable**. `TextPage` gives every
text kind a whole page and a plain textarea over its literal bytes; what it
never does is offer fields. Editing text is not the same promise as editing a
document whose shape studio claims to understand, and the second one is the one
that breaks every time the pipeline ships.

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
  button, so it counts — and so is `Dropdown.Trigger`. `ItemActions` and the
  tile's checkbox are therefore always *siblings* of the opening button,
  positioned over it (`MediaTile`) or beside it (`FileRow`, `FolderCard`) —
  which is why those three carry their frame on a wrapper `<div>` rather than on
  the button. Anything else that lands in a listing has to be built the same
  way. Its feedback is inline for the same reason the viewer's is:
  `ViewerChrome` is often inside a fullscreen element, and a toast portalled to
  `<body>` is not painted while one is.
- **A row's actions live in one `⋯` menu; the viewer's stay inline.** That split
  is not inconsistency, it is the fullscreen constraint again. `ItemActions` uses
  `Dropdown`, which is absolutely positioned inside its own relative wrapper and
  therefore fine on a row — but `MovePicker` uses `Dialog`, which **portals to
  `<body>`**, so it is reachable only from the browse page and there is
  deliberately no move button in `ViewerChrome`. If you ever want one there, it
  has to be built inline the way `RenameForm` and `ConfirmDeleteButton` are, not
  by reaching for the picker.
- **Rename is opened by the row, not by the button.** `RenameForm` is the field;
  `RenameButton` is a pencil that opens one in place and is now used only by
  `ViewerChrome`. The rows drive `RenameForm` themselves and render it
  `basis-full` on a wrapped line, because when it was a flex child of the control
  strip it rendered about forty pixels wide. A parent that knows a rename is open
  is what makes the field typeable — keep it that way.
- **The media grid has a selection mode, and it changes what a press means.**
  Once anything is selected (`useSelection`), pressing a tile extends the
  selection instead of opening it — the photo-library bargain, and the only way
  to pick forty tiles on a touch screen without hunting forty checkboxes. Escape
  clears, but only when no overlay is open, because the reel, the text page and
  the move picker each bind Escape to their own close — and the picker is often
  open *on* the selection, so clearing it there would be Escape cancelling a move
  by emptying what was being moved. Selection is keyed by object key rather
  than by grid index: a listing can be re-fetched underneath one — every write
  does exactly that — and an index-keyed selection would quietly come to mean
  different files.
- **The URL is the S3 key, and CloudFront has to be in on it.** `utils/location`
  maps `projects/<project>/runs/x/output/clip.mp4` ⟷
  `/projects/<project>/runs/x/output/clip.mp4`, segment-encoded so spaces and `#` in
  real filenames survive; a trailing slash means a folder, exactly as it does in
  S3. With the browsable root empty the two sides are now the same string, but
  it stays a mapping: `ROOT_PREFIX` there has to agree with the backend's
  `media_root_prefix`, and that is the seam where they meet. The catch is that a share link
  *ends in `.mp4`*, so the viewer-request function in `modules/hosting` routes by
  **location** (`/assets/…` and `/index.html` pass through, everything else
  rewrites) rather than by "does this look like a file". The old
  extension-matching version sent every share link to S3, where the 403/404
  fallbacks rescued it into `index.html` — it worked, by accident, one wasted
  origin round trip at a time.
- **The reel is sized in `dvh`, not `inset-0`, and sound lives in the top bar
  because of it.** `index.html` asks for `viewport-fit=cover`, so a `fixed`
  element pinned to all four sides is laid out against the *large* viewport —
  the one with the browser's toolbars hidden — and mobile Safari then draws its
  bottom toolbar over the result. Anything on the bottom edge of the reel was
  underneath it and unpressable. That swallowed the mute button in portrait and
  gave it back in landscape, where the toolbar collapses, which is how the bug
  was reported: "there is no way to mute unless I turn the phone sideways". The
  fix is `.reel-shell` (`height: 100dvh`, which tracks those toolbars) plus
  `env(safe-area-inset-*)` padding on both bars — but the transport bar is still
  the one edge of the screen a browser puts its own chrome on, so **sound moved
  to `ViewerChrome`** and only the scrubber stayed. Keep controls you press
  *while a clip is playing* out of the bottom bar.
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
- **One picker, two verbs.** `DestinationPicker` serves both move and copy,
  because "browse to a folder and press the button" is the same interaction
  either way and a typed prefix is useless against folder names that are
  timestamps. `verb` rides on the picker's target state rather than sitting
  beside it, so there is no way to have one open with no operation chosen. The
  single behavioural difference: a move into the folder the items are already in
  is disabled as a no-op, while a **copy** into it stays enabled, because that is
  how a file is duplicated and the server numbers the second one.
  Folders get `Move…` only — there is no folder-copy endpoint — which is why
  `ItemActions` takes `onCopyTo` as optional.
- **Every write re-fetches the listing rather than patching state.** A rename
  changes an item's position under `newest` and certainly under `name`; replaying
  that into a sorted array correctly is more code than one request, and it is
  code that would be wrong exactly where nobody tests. Three exceptions, for
  different reasons: the recursive reel drops a deleted item locally
  (`useReel.dropItem`) because re-walking would shift every already-loaded page
  under the scroll position; a **folder** move does not clear the selection
  because there was none; and deleting the folder you are *in* skips the refresh
  because the prefix it would refresh has just stopped existing — going up is
  what re-fetches. A copy *does* re-fetch, unlike the favouriting it
  replaced: its destination can be the folder you are looking at, so the listing
  on screen may genuinely have changed.
- **The folder you are in is deleted from the action row, not from a menu.**
  Every other folder carries its own `Move…`/`Delete` in an `ItemActions` menu on
  its card — but that card is drawn by the folder's *parent*, so the one folder
  with no card on screen was the one you were standing in, and getting rid of it
  meant navigating back out to find it in the grid. `BrowsePage` puts a
  `ConfirmDeleteButton` (tone `bar`) in the action row, disabled at the root
  where `keys.assert_inside_root` refuses it anyway. Leaving is the one
  navigation between folders that **replaces** rather than pushes: the entry
  behind you would otherwise be the prefix you just destroyed.
- **The three folder icons are one cluster, and the rule before "Play reel" is
  load-bearing.** Copy prefix, delete this folder and new folder all act on the
  folder you are in, so they sit together at a tighter gap than the row's own —
  which is why copy moved down out of the breadcrumb row, where it had been
  stranded away from the other two. `Play reel` is the only filled button on the
  page, and a delete flush against it is a mis-click with no undo, so the
  destructive icon stays in the middle of the cluster and a `w-px` divider
  separates the cluster from the primary. The two rows now split exactly as the
  comment above them claims: *where you are* on top, everything you can *do*
  below.
- **Destructive confirmation is in the button, never in a dialog.**
  `ConfirmDeleteButton` arms on the first press, names what it will destroy, and
  disarms on a timeout, on blur, or on Escape. A portalled dialog is not painted
  while a `<video>` is in native fullscreen — the same constraint that keeps
  `CopyKeyButton`'s feedback inline — and a dialog in a fixed position trains a
  second click that lands before anyone reads it.
- **`services/keys.py` is the only thing between a query string and
  `GetObject`.** Every prefix and key is normalised and confined to
  `config.media_root_prefix()`. That root is empty in prod, so the confinement
  check passes everything and the traversal rules (`..`, a leading `/`, a
  backslash — all rejected before normalisation) are what is actually holding
  the line. Test changes to it directly — `posixpath.normpath` strips a trailing
  slash, which is why the folder check happens on the raw value, and it is why
  the tests set a non-empty root to keep the confinement branch covered.
- **`.heic` is not in `IMAGE_EXTENSIONS`, and a couple of seed photos are
  `.heic`.** They list as ordinary files rather than tiles. That is the current
  behaviour, not a considered decision — but before adding the extension, note
  that Chrome cannot decode HEIC, so a tile would render as a broken image
  rather than a photo.
- **The Lambda's env vars come from the deploy workflow, not from Terraform.**
  `lifecycle { ignore_changes = [environment] }` means the `environment` block
  in `modules/compute` only applies the first time the function is created;
  after that the `jq` block in `studio-prod.yaml`'s `update-lambda` job is the
  only thing that sets `STUDIO_MEDIA_ROOT_PREFIX`. Change one without the other
  and the value you read in the code is not the value that is running. It is
  also legitimately the empty string — do not "fix" it by dropping the line.
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

**`GET /api/libraries` is the one route that is authenticated without being
about a library.** It answers "which libraries am I in", which is where the id a
client puts in `X-Studio-Library` comes from, so it has to be reachable before
one has been chosen. A caller who is in none gets an empty list and a 200, never
a 403: "you are in no libraries" and "you asked for one you are not in" are
different problems with different fixes, and this route is how the first one
gets found.

**A node is `{id, lib, parent_id, name, kind, size, content_type, created_at,
updated_at}` and never `blob_key`.** The view is an allowlist rather than a
`pop`, so an attribute added to a record is invisible to a client until someone
adds it here on purpose. The S3 key stays internal because it is *meaningless* —
prod holds `characters/<slug>/…` keys written years before the catalog alongside
`blobs/<node_id>` keys written after it, and both are correct forever only for as
long as nothing outside `services.catalog` parses one. `path` is withheld too,
for a weaker reason: it is a materialised index of ancestor ids that a move
rebuilds, and `parent_id` answers the same question authoritatively.

**Every node response is membership-checked against the node's own `lib`**, not
against the library the request claimed. A node id is a v4 UUID, so this is not a
guard against guessing; it is the guard against a *shared* id once a library has
more than one member. A node that does not exist is 404 before that check can
run, which is safe for the same reason — an id nobody was given cannot be
reached.

**`GET /api/nodes` is one query plus `ceil(n / 100)` batched reads, and that is
the shape to keep.** The by-parent item carries the index projection only
(`node_id, lib, kind, path, created_at`), so `size` and `content_type` come from
a `BatchGetItem` over the `META` rows. Widening the projection would make the
listing a single query and put a mutable copy of every file's metadata on a
second item, which every rename and every text edit would then have to keep in
step (#309). `UnprocessedKeys` comes back on a **200**, so botocore's retries
never see it — `catalog.records` retries it explicitly and raises rather than
answering with a short listing.

| Route | Returns |
|---|---|
| `GET /api/health` | `{"status": "ok"}` — liveness, touches no S3 |
| `GET /api/libraries` | `[{id, name, role}]` — the caller's libraries. Authenticated, **not** library-scoped |
| `GET /api/nodes?parent=` | The children of one folder, name-ascending. 404 unknown parent, 403 another library |
| `GET /api/nodes/<id>` | One node. 404 unknown id, 403 another library |
| `GET /api/resolve?path=` | A slash-joined name path → the node it names. An empty path is the library root |
| `POST /api/nodes` | `{parent, name, kind, blob_key?}` → creates a folder or a file. **201.** 409 if the name is taken |
| `PATCH /api/nodes/<id>` | `{name}` to rename **or** `{parent}` to move — both at once is a 400, not a guess |
| `DELETE /api/nodes/<id>` | Node and subtree. Rows first, then blobs |
| `GET /api/nodes/<id>/download-url` | A fresh presigned GET for the node's blob. `disposition=attachment` to download |
| `GET /api/tree?prefix=&sort=` | One delimited listing: `folders`, `files` (each presigned), `breadcrumbs`, `counts` |
| `GET /api/reel?prefix=&cursor=&page_size=&sort=` | Images and video beneath a prefix, recursively, paginated |
| `GET /api/asset?key=&disposition=` | A fresh presigned URL for one object |
| `GET /api/text?key=` | A `.json` / `.md` / `.txt` object's contents, capped at 1 MB |
| `POST /api/folder` | `{prefix, name}` → creates an empty folder. 409 if taken |
| `PATCH /api/object` | `{key, name}` → renames one object in place. 409 if taken |
| `PATCH /api/folder` | `{prefix, name}` → renames a folder and its subtree |
| `POST /api/objects/move` | `{keys: [...], destination}` → moves 1..N objects, names kept. 409 if taken |
| `POST /api/folder/move` | `{prefix, destination}` → moves a folder and its subtree |
| `POST /api/objects/copy` | `{keys: [...], destination}` → copies 1..N objects, sources kept. Names numbered if taken |
| `PATCH /api/text` | `{key, content}` → overwrites an existing text file |
| `DELETE /api/objects` | `{keys: [...]}` → deletes 1..N objects |
| `DELETE /api/folder` | `{prefix}` → deletes a folder and its subtree |

**Rename and move are separate routes and must stay separate.** A rename takes a
`name` and changes the last segment; a move takes a `destination` prefix and
changes the folder. `keys.clean_name` refuses a slash, so a rename cannot become
a move by punctuation, and a destination is always read as a prefix, so a move
cannot become a rename by typing a filename into it — `move(x.jpeg → a/b.jpeg)`
puts the file *inside* `a/b.jpeg/`. That asymmetry is deliberate and the tests
pin it.

**`POST /api/objects/copy` is `move` minus the delete, plus numbering.** Same
body, same confinement at both ends, same bulk cap. Two differences, both
deliberate:

- **A name the destination already holds is numbered, never refused.**
  `clip.mp4` lands as `clip (2).mp4` — the convention the bucket already holds
  from folders filled by hand. A move refuses the whole request on a conflict
  because a half-done move splits a selection across two folders with nothing to
  say where the boundary fell; a copy has no such split, and copying a file into
  a folder that already holds the name is ordinary rather than a mistake.
  Nothing is ever overwritten in either.
- **Numbering looks at names only.** It does not compare sizes to decide that an
  identical file is "already there" and skip it. That was how favouriting
  behaved, and it is a copy quietly deciding not to copy. Ask for a copy, get a
  copy.

**`PATCH /api/nodes/<id>` refuses `name` and `parent` together.** On the
key-addressed side rename and move are different routes, and `keys.clean_name`
refuses a slash so a rename cannot become a move by punctuation. Collapsed onto
one verb, the separation has to be stated instead: the two orderings give
different answers when the destination already holds that name, and choosing one
silently is how a file ends up somewhere nobody looks for it.

There is no `POST /api/folder/copy`: a subtree copy can be arbitrarily large with
no progress to report, and nothing has wanted one yet. Argue for it separately.

**`PATCH /api/text` is a PATCH because PUT is not in the CORS method list.** The
verb list lives in four places that have to agree (see below), PATCH is already
in all four, and the semantic difference is worth less than the agreement. Add
PUT properly if a route ever genuinely needs it.

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

`dev-setup.sh` writes `frontend/.env.local` from SSM and installs
`frontend/node_modules` — do not hand-copy the example or hand-edit the result;
the generated file says as much in its own header. Without the env file the app
shows "Auth is not configured"; without node_modules every local binary is
missing, and the first one you hit is `tsc: not found`.

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
