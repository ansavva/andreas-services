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
`s3://xharness-prod-media-us-east-1/`. Studio makes that browsable:
folders keep their structure, images and video are the focus, and every item can
be opened fullscreen or flipped through as a vertical reel.

**Studio reads the library and tidies it — it does not produce it.** It browses,
and it can rename, move, delete, create folders, favourite, and edit the text
files in place. It cannot upload, and it cannot generate: making media is the
pipeline's job, and the pipeline runs locally under a human's own AWS login, not
through this API. That is a narrower boundary than the one this file used to
describe ("a reader and only a reader"), and the reasoning behind the change is
in **What this service may do to the bucket** below.

The line between "edit a text file" and "upload" is worth stating, because it is
thinner than it sounds and is held in exactly one place: `manage.update_text`
refuses a key that does not already exist.

**Favouriting is the one write that adds an object, and the distinction that
keeps it honest is where the bytes come from.** A favourite is a server-side
`CopyObject` of something already in the bucket, so nothing arrives from
outside; what studio still cannot do is put bytes in that were not there
already. Every write it accepts either copies, moves, overwrites or removes
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

`xharness-prod-media-us-east-1` is studio's own bucket, declared in
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
- **A favourite is a copy that keeps its source, and it is the only one.** Every
  other `CopyObject` here is the first half of a rename or a move and is
  followed by a delete. `manage.favorite_objects` is not, which means it is also
  the only write that *adds* an object rather than relocating one — see the
  correction at the top of this file. The bytes still come from inside the
  bucket, so "studio cannot upload" is untouched by it.
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
│   └── <face|body|scene|wardrobe>/   #   sometimes split by category
└── archive/                    # superseded output kept around
projects/<subject>/             # what was generated of them
├── runs/<ts>_<slug>/           # request.json, result.json, sometimes prompt.json
│   └── output/                 # the generated .jpeg / .webp / .mp4
├── scenes/<ts>_<slug>/         # scene.json + shots/ + output/, a stitched sequence
├── chains/<name>.json          # a scene's shot-to-shot plan
└── favorites/                  # picked output, copied flat — studio writes here
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
`media_root_prefix` is the first knob that matters. It is no longer the only
one: **favourites made studio name two folders**, and they are the only two.

```
STUDIO_PROJECTS_PREFIX    projects   # what a "project" is, relative to the root
STUDIO_FAVORITES_FOLDER   favorites  # the shelf inside one
```

Both live in `config.py` beside `media_root_prefix`, both default to what the
bucket actually holds, and neither is set by Terraform or the deploy workflow —
the defaults are the intended values, so there is nothing here to drift out of
step the way `STUDIO_MEDIA_ROOT_PREFIX` can. **Setting either to the empty
string turns favouriting off entirely**, which is the deliberate failure mode:
if the pipeline reshapes the bucket again, a missing star is a much better
outcome than copies landing in a folder that no longer means anything. Nothing
else in studio names a folder, and nothing else should start to.

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
- **The star is state, not a receipt.** `FavoriteButton` renders lit from the
  listing's own `favorited`, so it reports the folder rather than the press —
  which means it is right after a reload and right about a file favourited from
  another device. It is keyed by `file.key` in `ViewerChrome` because that bar
  stays mounted while the reel scrolls underneath it, and without the key the
  last clip's "added" state would be painted onto the next one. Files that
  cannot be favourited never render it at all: `favorites_prefix` is null and
  the button does not exist, which is how `characters/` gets no star without the
  frontend knowing anything about the bucket's shape.
- **Every write re-fetches the listing rather than patching state.** A rename
  changes an item's position under `newest` and certainly under `name`; replaying
  that into a sorted array correctly is more code than one request, and it is
  code that would be wrong exactly where nobody tests. Two exceptions, for
  opposite reasons: the recursive reel drops a deleted item locally
  (`useReel.dropItem`) because re-walking would shift every already-loaded page
  under the scroll position, and **favouriting does not re-fetch at all** —
  the copy lands in a folder you are by definition not in (an item inside
  `favorites/` cannot be favourited), so the listing on screen is unchanged and
  a refresh would be a request whose only visible effect is a flicker.
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
| `POST /api/objects/move` | `{keys: [...], destination}` → moves 1..N objects, names kept. 409 if taken |
| `POST /api/folder/move` | `{prefix, destination}` → moves a folder and its subtree |
| `POST /api/favorites` | `{keys: [...]}` → copies 1..N media files into their own project's `favorites/`. No destination |
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

**`POST /api/favorites` takes no destination, and that is the whole design.**
Move takes one and will put a file anywhere; favourite derives it from the key
(`keys.favorites_prefix`) so there is exactly one legal answer per file and no
argument that could aim it elsewhere. That is what lets one request favourite a
selection spanning two subjects — each file goes to its own project — and it is
why favouriting from `characters/` is a 400 rather than a copy into a guessed
folder. Three more consequences worth knowing:

- **The folder is flat, so names collide, and that is ordinary rather than an
  edge case** — every scene calls its first shot `shot-01.mp4`. Same name and
  same size is read as "already favourited" and **skipped**; same name and a
  different size is **numbered** (`shot-01 (2).mp4`, the convention the folder
  already holds from being filled by hand). Nothing is ever overwritten.
- **Only images and video**, the same two kinds the reel shows. A `result.json`
  copied flat onto the shelf beside the clips is noise, and the listing endpoints
  apply the same rule so the star and the API cannot disagree about what is
  acceptable.
- **`favorited` on a listing is read from S3, not remembered.** Studio holds no
  state, so `browse._mark_favorited` lists the favourites folder once per listing
  (once per project on a reel page) and matches on name and size. That costs one
  extra `ListObjectsV2` and buys a star that survives a reload — without it the
  UI could only report presses from this session, and would go hollow over a file
  that is very much still favourited. There is no un-favourite route: deleting
  the copy from inside the favourites folder is unambiguous, and `DELETE
  /api/objects` already does it.

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
