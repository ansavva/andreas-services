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

**The library is a DynamoDB table; the bucket is where its bytes happen to
live.** Every folder, name, parent, size and timestamp is a row in
`studio-prod-catalog`, and an S3 key is an opaque `blob_key` on a row that
nothing outside `services/catalog.py` parses. Nothing lists the bucket to find
out what exists.

That is what makes a rename move no bytes, a share link survive one, a library
have more than one member, and a folder reachable through `parent_id` without a
string being cut on `/`. What it costs is that a lost row is a lost file even
though every byte of it survives — S3 versioning does not reach a row, and the
table's PITR is its only recovery. See [../infra/README.md](../infra/README.md).

The generation pipeline produces the media and records it through the API.
Studio makes the result browsable: folders keep their structure, images and
video are the focus, and every item has a page of its own where it plays in
place, with the feed it belongs to beside it.

**Studio reads the library, tidies it, accepts bytes for it, and submits a
run when a person presses Send — it does not decide what to make.** It browses;
it can rename, move, copy, delete, create folders, edit text files in place, and
upload through a presigned PUT the bytes travel to directly. Planning a
generation is the pipeline's job and the SPA's create bar; the payload behind
the opened run's Request row is what `POST /api/runs/<id>/submit` sent.

The line between "edit a text file" and "upload" is held in exactly one place:
`manage.update_text` refuses a node that is not a file carrying a blob, which
also refuses a placeholder whose upload never landed.

**Copying is the one write that adds an object, and what keeps it honest is
where the bytes come from.** A copy is a server-side `CopyObject` of something
already in the bucket. Bytes from outside enter only through
`POST /api/nodes/<id>/upload-url`.

**The SPA drives that upload.** There is an Upload button on the folder toolbar;
it takes any number of files, puts them into the folder on screen, and does
nothing character-aware or project-aware — a folder is a folder. **An uploaded
file keeps the name it arrived with**, and a name the folder already holds is
*numbered* (`clip.mp4` → `clip (2).mp4`) rather than refused or overwritten,
the same form `POST /api/nodes/copy` produces. The pipeline's
`<project>_in_<n>.<ext>` input-pool numbering is the pipeline's convention
(`projects.add_inputs` reads the highest N off the names); it is not the app's
business what a folder's names mean.

The numbering happens **in the API** (`catalog.create_numbered`), not in the
browser. A client-side version would be a second implementation of a convention
that has to agree with copy's, and it would pick a name from a listing that is
already stale by the next file — the conditional put on the `NAME#` item is the
only authority on whether a name is free.

## Stack

| Layer | Choice |
|---|---|
| Backend | Flask (Python 3.11) + Mangum, Docker container Lambda behind API Gateway REST |
| Frontend | Vite + React 19 + Tailwind v4 + the design system's **web** leaves, static build to S3 + CloudFront |
| Auth | AWS Cognito (admin-create-only user pool); **Cognito Managed Login** (hosted pages at `studio-auth.andreas.services`) with the authorization-code flow + PKCE on the SPA, Cognito authorizer on every `/api` route. The `studio` CLI signs in with SRP directly — see `infra/modules/auth`. |
| Data | **DynamoDB, single-table** (`studio-prod-catalog`) — one item pair per node, three `ALL`-projected GSIs (`by-sk`, `by-path`, `by-recent`). No cache. Listings are a query. |
| Blobs | S3, addressed only by a row's opaque `blob_key`. Never listed. |
| Routing | By node id. `/f/<id>` is a folder, `/o/<id>` is one open file. |
| Media | Presigned S3 GET URLs, direct from the browser to S3 |
| Infra | Terraform in `studio/infra/` (`modules/` + `envs/prod` + a per-machine `envs/dev`) |

A node id never changes, which is why both the routing and the share links are
built on it: a key changes when a file is renamed, an id does not.

## Directory Structure

```
studio/
├── backend/                  # Flask + Dockerfile, shipped as a container Lambda
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── studio_core/          # routes → services → clients
│   │   ├── routes/           # one blueprint per resource: nodes, libraries, browse,
│   │   │                     #   characters, projects, runs, scenes, movies, renders,
│   │   │                     #   images, models, templates, tags, phrasebook, prompt
│   │   ├── services/         # catalog.py owns the item shapes; browse.py, manage.py,
│   │   │                     #   identity.py (JWT), keys.py (classification + naming),
│   │   │                     #   generate.py + callbacks.py (the paid call and its webhook),
│   │   │                     #   render.py (the queue the worker image drains),
│   │   │                     #   layout.py (an entity's folder shape).
│   │   │                     # storyboard.py, prompt.py, registry.py and digest.py are
│   │   │                     #   loaded by path from the PIPELINE's test fake, so
│   │   │                     #   none of the four may import Flask or boto3
│   │   ├── clients/aws/      # dynamodb.py, s3.py, sqs.py, ssm.py — the only boto3 in the service
│   │   ├── clients/replicate.py
│   │   ├── handlers/         # aws/ (api, hook, render, worker) and local/ (dev server, consumers)
│   │   └── media/            # ffmpeg.py, imaging.py, sheet.py, workspace.py — the render worker's tools
│   └── tests/                # unit/ (pytest + moto), integration/, smoke/
├── frontend/                 # Vite + React SPA (studio.andreas.services)
│   ├── index.html            # pins data-theme="dark"
│   ├── e2e/                  # Playwright specs over committed /api fixtures
│   └── src/                  # apis, components, pages, hooks, context, utils, types
│                             # routes.tsx is the URL table; *.test.tsx is vitest
├── infra/
│   ├── modules/              # auth, compute, api_gateway, api_domain, hosting, media,
│   │                         #   catalog, callbacks, render, dev_storage, dev_seed
│   ├── envs/prod/            # applied by CI
│   └── envs/dev/             # per machine, applied only by scripts/dev-aws-*.sh
├── pipeline/                 # the generation half's code — local only, never deploys
├── scripts/                  # create-user.sh, add-member.sh; dev-setup.sh / dev-up.sh;
│                             #   dev-aws-{setup,reset,destroy,seed}.sh, dev-shared-material.sh,
│                             #   dev-user.sh, dev-token.sh, dev-test-integration.sh;
│                             #   dev_seed/ (its own uv project);
│                             #   prod-seed-smoke.py, prod-github-set-secrets.sh
├── .claude/skills/           # the generation half's docs — local only, never deploys
├── docs/
│   ├── PIPELINE.md           # the local half
│   ├── ENTITY_MODEL.md       # the data model, with ENTITY_MODEL_EXAMPLE.md and RUN_PLAN.md
│   ├── PROD_SMOKE.md         # the post-deploy smoke run
│   └── WEB_APP.md            # ← this file
└── CLAUDE.md                 # the index over both
```

## What this service may do to the library

Two stores, and only one of them has a boundary IAM can describe.

`studio-prod-media-us-east-1` is studio's own bucket, declared in
`infra/modules/media`; `studio-prod-catalog` is studio's own table, declared in
`infra/modules/catalog`. The pipeline runs from a laptop and holds **no AWS
credentials at all** — it signs in with `studio login` and comes through this
same API. This Lambda is the only thing reachable from the internet, so it is
the thing worth scoping.

### The S3 grant, which confines nothing

The API role's policy (`modules/compute`, `media_access`) grants four actions
on the whole bucket: `s3:ListBucket`, `s3:GetObject`, `s3:PutObject` and
`s3:DeleteObject`. There is no prefix condition — a `blob_key` is opaque, so
there is no string an IAM condition could match that means "this library".

What the grant does and does not allow:

- **`services/keys.py` is classification and naming.** `clean_name` refuses a
  slash, a `.`, a `..` and a control character, so a rename cannot become a move
  by punctuation. "Delete the library" is not expressible because the root node
  has no `parent_id` and so no `NAME#` item to rewrite. `keys.kind` and
  `keys.language` classify by extension.
- **Upload is a signed PUT; there is no multipart grant.**
  `POST /api/nodes/<id>/upload-url` signs a PUT and
  `POST /api/nodes/<id>/confirm-upload` finalises the row once `HeadObject`
  succeeds. The bytes never transit the Lambda, which is how the 6 MB request
  limit is avoided. What bounds it is the signature, not the policy: one key
  (`blobs/<node_id>`, never one the caller names), one exact content length, one
  content type, and a TTL shorter than a read URL's. `content-length` and
  `content-type` are signed headers, so an oversized body is refused by S3.
  `max_upload_bytes` is S3's single-PUT ceiling rather than a policy number.
  The only other `PutObject` is an overwrite of an *existing* text file
  (`manage.update_text`, capped at `max_text_bytes`).
  **A failure between the row and the bytes leaves a placeholder.** The node is
  minted first, because its id names the key, so anything that fails after that
  leaves a row naming `blobs/<id>` with nothing behind it.
  `browse.is_abandoned_upload` keeps it out of listings and out of the feed,
  keyed on `size` being **absent** — `"size" in record`, not truthiness, because
  a confirmed empty file has `size` 0 and a placeholder has no `size` at all.
  The SPA's uploader deletes the node itself when a PUT fails; the hidden row is
  what is left when that cleanup fails too. Nothing collects it.
- **`copy_objects` is the only `CopyObject`.** Rename, folder rename and move are
  catalog transactions that move no bytes. Each copy gets its own object rather
  than a second row pointing at one key — `catalog.delete_node` does not ask
  whether a blob is still referenced, so a shared key would mean deleting one
  copy destroyed the other's bytes.
- **`s3:DeleteObjectVersion` is deliberately absent**, and the bucket **is**
  versioned (`infra/modules/media`), so this role can only write tombstones,
  not erase history. Every delete of an *object* it can perform is recoverable.
  With no prefix confining anything, this is the strongest guarantee standing —
  do not drop it to tidy the policy.
  **It says nothing about a row.** `DELETE /api/nodes/<id>` removes rows first
  and blobs second, so a delete that half-succeeds leaves recoverable bytes
  nothing can name.

### The catalog grant, and why the boundary is not in IAM at all

Neither the S3 grant nor the DynamoDB one can express the security boundary:

- **A row has no prefix to scope by.** `blob_key` is opaque.
- **Membership is a table lookup, not an identity.** Whether a caller may see a
  node is answered by a `USER#<sub>` query, on rows the same policy grants
  access to. IAM cannot ask a question whose answer is in the data it is
  guarding.
- **Two nodes in different libraries are two items in one partition space.**
  `lib` is an attribute, and a key you can move an item across is not a key
  you can authorise on.

So the policy's job is narrow — `GetItem`, `BatchGetItem`, `Query`, `PutItem`,
`UpdateItem`, `DeleteItem` and `TransactWriteItems` on this table and
`<arn>/index/*`, and nothing that changes what the table *is*. `Scan` is absent
because a scan crosses library boundaries by construction. `BatchWriteItem` is
absent because a node is two items and every write is a `TransactWriteItems`.
`CreateTable`, `DeleteTable` and everything touching PITR are absent because
nothing reachable from the internet should be able to delete the library.

**What holds the line is membership, checked inside the API.** Every node
response is checked against the node's own `lib` — not against the library the
request claimed — because a node id is shareable and the node's own answer is
the only authoritative one. `before_request` in `app_factory.py` resolves the
caller's library once per request from `X-Studio-Library`, a sole membership,
or a refusal. That is the boundary, and it is the reason the API is the only
writer to this table.

**The consequence for reviewers: an IAM diff cannot tell you whether the
boundary moved.** Anything that widens who can see what is a change in
`routes/nodes.py`, `routes/libraries.py` or `app_factory`'s request hook, and
reads as ordinary application code. Do not read a clean Terraform plan as
evidence.

**A row has no version history.** A move rewrites `path` across a whole subtree and leaves nothing behind. The catalog's only recovery
is the table's PITR, restored out of band by a human into a new table, plus
`deletion_protection_enabled` refusing a `DeleteTable` at the API rather than
only in Terraform.

### The bucket's own protections

There is **no second copy of this bucket anywhere.** Versioning and
`prevent_destroy` are what stand in a mirror's place.

## What the library looks like

**The tree below is the catalog's, not the bucket's.** Rows carry the names,
the parents and the shape; the bucket carries bytes under whatever key a row
happens to point at. Read the diagram as the folder tree a person sees.

**A `blob_key` is `<characters|projects|libraries>/<entity id>/<node id>.<ext>`**,
stamped once when the node is created from the owner its parent already
resolves to; `catalog.blob_key_for` is the single definition. It carries an id
and never a name, so a bucket listing does not spell out any character in the
library — hard rule #1 applied to the one place that could otherwise break it.

**It is a pointer with no meaning in it.** A rename does not touch it, a move
does not touch it, and nothing outside `services/catalog.py` may split it on
`/`. The prefix is an operational convenience — per-entity cost in Storage
Lens, a lifecycle rule, a bulk delete that is one prefix — not an address. Move
a file between entities and the prefix goes stale while the key stays correct;
a stale prefix is cosmetic and nothing corrects it.

**`is_api_blob` gates whether a signed upload may overwrite an object.** A
signature makes a refusal permanent the moment the URL is handed out, so do not
narrow what it accepts without checking every key shape the bucket holds.

Because a row and a blob are deleted separately, a blob can outlive every row
that pointed at it. The delete does not throw that answer away:
`catalog.open_sweep` writes the keys a delete is about to free onto a `SWEEP#`
row *before* the rows naming them go; `manage.release` closes that row once the
bytes are gone; `manage.drain` finishes any sweep an earlier request abandoned,
rechecking each node id so a crash between open and delete cannot collect bytes
a live row still names. The orphan is addressed rather than searched for, so
there is no scan. `backend/tests/unit/test_sweeps.py`.

**There is no `media/` wrapper.** The browsable root is the library root node.

```
<character>/                    # a character's folder; its record names it `root`
├── seed/                       # source photos
├── corpus/                     # the wider photo set
├── reference/                  # where its identity images conventionally sit
└── archive/                    # superseded output kept around
<project>/                      # a project's folder
├── runs/<run id>/              # the run's documents
│   └── output/                 # the generated .jpeg / .webp / .mp4
├── scenes/<scene_id>/          # storyboard/ + shots/ + output/
├── movies/
├── chains/                     # a scene's shot-to-shot plan
└── input/                      # the working pool
config/angle/                   # the angle images; source of truth is the repo
```

`services/layout.py` holds the two shapes: `CHARACTER_LAYOUT` is `reference`,
`corpus`, `seed`, `archive`; `PROJECT_LAYOUT` is `runs`, `scenes`, `movies`,
`chains`, `input`.

**No `characters/` or `projects/` wrapper**, and no `profile.yaml`,
`project.json`, `scene.json` or `movie.json`. Each of those is a row. An
entity's folder is a top-level node its record names, so the two are found in
opposite directions: the record names `root`, and the root node carries
`entity` back. The bible, the project's description, a scene's shot list and a
run's envelope are all rows. What stays a file is what studio does not own: a
run's payload documents are the provider's bytes, served as text and never
parsed.

Two things about this shape drive the UI: run and scene folders sort
chronologically because their names start with a timestamp, and a run's output
lives one level down in `output/`, so a run folder itself usually shows only
JSON. A folder is a row, stamped by `catalog._now` like every other row, so a
folder has a `last_modified` and date sorts need no fallback to its name.

**Nothing in studio names a folder the pipeline owns, and nothing should start
to.** A copy is handed its destination; studio does not know which folder inside
a project is special.

**The run's payload documents are deliberately not parsed.** The pipeline owns
their shape and changes it freely, so studio serves those files as text and the
frontend shows them as text. Do not start decoding them into typed UI — the
moment the pipeline adds a field, a parser becomes a liar. That holds even
though text files are **editable**: `TextPage` gives every text kind a whole
page and a plain textarea over its literal bytes, and never offers fields.

## Conventions & gotchas

- **The shell is a sidebar and a top bar, and every screen renders inside
  `AppLayout`.** `AppSidebar` is the design system's `Sidebar` — 256px, or a
  64px icon rail — holding the five sections (`DESTINATIONS`), the five most
  recently updated projects, the library switcher and the account menu. The
  collapse state is `SidebarContext`'s, not the package's own, so the opened
  run can collapse the rail from a route element: `useShellSidebar()` gives
  `{ collapsed, setCollapsed, toggle }`, mirrored into `localStorage` under
  `SIDEBAR_STORAGE_KEY`. `TopBar` is full width and sticky — `CreateBarSlot`
  (the create bar's mount point, empty until that lands) and then
  `HeaderSearch`. Below `md` the sidebar is not drawn: a menu `IconButton`
  opens the same `SidebarContents` in a `Drawer`, and search sits behind an
  icon. `--header-h` in `app.css` is the bar's height at both widths; content
  is full width with the mockup's `px-6`, no `max-w-*` cap.
- **The logo is a function, not a file, and the favicon is generated from it.**
  `src/utils/aperture.ts` solves a six-blade iris at any openness;
  `components/common/Aperture.tsx` draws it twice from that one construction —
  `ApertureMark` in the sidebar, and `ApertureSpinner`, the same mark with
  `openness` moving, at every loading call site. A browser tab cannot import a
  module, so `npm run mark` renders `src/assets/aperture.svg` from the same
  function and `npm run mark:check` fails the PR when the committed file has
  drifted. **Edit the geometry and re-run `npm run mark`** — never the SVG. It
  goes through Vite's asset pipeline rather than `public/`, so it comes out
  content-hashed and the deploy's `immutable` cache-control is right for it.
- **A project's Runs tab is the feed, and it is the default tab.** `RunFeed`
  draws one row per run, newest first, grouped by day — outputs on the left,
  the plan on the right — from one `GET /api/runs?view=feed` page per scroll,
  so no row fetches anything. `?q=` is the prompt search on the feed itself,
  applied on Enter; status, character, model and since ride in the address
  like the browser's own filters. A run in flight fills its row with
  full-size `studio-shimmer` tiles carrying the aperture spinner and the
  seconds since it went out, the feed polls (`FEED_POLL_MS`) while any row is
  in flight, and `useInFlightRuns` reads those same cached pages for the
  "N running" badge in the project header and the spinner beside the project
  in the sidebar — which is why both are only ever right about projects open
  this session. Hover a tile for its own actions (download, Use in prompt,
  Again / Upscale / Animate / Promote — `OutputTile`); the run's are icon+word
  in its column (Rerun, Edit, Folder, Trash, More). Every one of them is
  `useRunActions`, which the opened run's grid draws too, so a gesture means
  one thing in both places. Settings, behind the gear at the end of the strip,
  is what Overview was; `?tab=overview` still lands there.
- **The opened run is a lightbox over the feed, not a page.** `/p/<project>/
  r/<run>` renders `ProjectPage` with `runId` set, and `RunLightbox` sits over
  the feed with the create bar live above it: the output large (`MediaPlayer`,
  so a clip plays in place), the run's other outputs under it, a strip of the
  project's runs along the bottom, and a rail holding the plan, the sends with
  their roles, the cast, one uniform action grid, and a collapsed **Request**
  row. It collapses the sidebar to its rail on open and restores it on close;
  Esc closes back to the project with `?tab` and the filters kept; Left/Right
  and the strip step through the rows the feed has loaded — the same
  `["runs", "feed", …]` cache, so opening a run costs no second listing.
  `getRun` is fetched for what a row does not carry: the folder, the
  prediction id and the payload nodes. A cold link with nothing cached draws
  the row off the record (`rowOfRecord`). The two-column `pages/RunPage.tsx`
  that used to answer this address is deleted.
- **An opened run shows three different kinds of thing, and conflating them is
  the one mistake to avoid.** The *envelope* is studio's and safe to render as
  fields. The *payload documents* are the provider's and are shown as text and
  never decoded — `PayloadDocument`, behind the Request row, fetched one
  document at a time and only when pressed. The *plan* is studio's too — the
  prompt, the params, and one ordered `SEND#` row per bound image with its
  role and provenance; `bindings` is derived from those sends. See
  [RUN_PLAN.md](RUN_PLAN.md).
- **There is no approve step in the app, and no approve route to call.**
  Decision 2026-09-04: pressing Send submits. The approve route is gone, and
  so are the `approved` status, the `approval` field and
  `plan_digest` on the record. The app claims no authority it does not have —
  the CLI holds the same kind of token — so what hard rule #2 buys here is that
  the payload is on screen before the button is.
- **Editing a plan is two writes.** `PATCH /api/runs/<id>/plan` and `PATCH
  /api/runs/<id>/sends` each replace their half whole and move the fingerprint
  — so an editor sends only the half that moved. Both routes refuse a
  submitted run, which is why Edit on a finished run loads it into the create
  bar as a NEW draft rather than being answered with a 409.
- **The app can submit.** `POST /api/runs/<id>/submit` is what calls Replicate;
  the SPA has no provider credential and never gains one, because the spending
  sits behind that route.
- **Running is ONE armed button, and pressing it is the act.** A draft's row
  and rail offer `Run`; a finished run's offer `Rerun` (`useRunAgain`: a new
  draft carrying the same plan and ordered sends, byte for byte, then
  `submit`). Either calls `POST /submit` and nothing before it. First press
  arms and says what the second will do; the second runs. See `useArmed`, the
  one arm/disarm machine `ArmedButton`, the lightbox's `ArmedCell`,
  `ConfirmDeleteButton` and `ItemActions` all run on.
- **A run's outputs can be promoted into a character, from the tile or the
  rail.** An image output's hover overlay and the opened run's grid both
  carry `Promote`, which opens `PromoteDrawer` — `PromotePanel` in a drawer
  beside the picture it is about, so the output stays on screen while the
  form is filled in. It makes a **real copy** into the character's
  `reference/` pool, then puts the `default` tag on the **copy**, so the run
  keeps its own output and every record citing it stays correct. Hard rule
  #2b is satisfied by the press itself — the person choosing the character and
  the group IS the approval — and the panel states plainly what it will do.
  Video outputs get no control: a reference is a picture a later render is
  checked against.
- **Every gesture that spends or destroys is arm-then-fire in the button
  itself.** `ConfirmDestroyDialog` remains for entity deletion and nothing on
  the run surface reaches for it; the promote drawer is the one overlay, and
  it declines a dismissal while it holds words.
- **A run closes itself, so the feed has something to poll and a reason to.**
  The prediction is closed by Replicate calling the API back, which is why
  `TERMINAL_RUN_STATUSES` exists: a client that knows which states can still
  change stops asking on its own — the feed through `inFlight`, the opened
  run's record through `isTerminal`. A run stuck at `running` long after it
  should have settled is `POST /api/runs/<id>/reconcile`, which the app no
  longer offers a button for: the CLI's `studio runs reconcile` is the tool.
- **The API takes the ID token, never the access token.** A REST
  `COGNITO_USER_POOLS` authorizer only reads the incoming token as an *access*
  token when the method declares `authorization_scopes`. This one declares none
  — and cannot usefully, since the pool has no resource server and the code
  flow's `openid email profile` are identity scopes — so it validates an
  *identity* token. Send the stored `idToken` (`auth/oauth.ts`, read by
  `apis/client.ts`). The failure mode is the confusing one: sign-in succeeds,
  the app renders, and every `/api` call 401s.
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
  frontend re-signs through `/api/asset?node=` from a media element's `onError`
  (`useSignedSrc`), capped at one retry per node.
- **A cross-origin `<a download>` is ignored by browsers.** Downloads work only
  because `/api/asset?disposition=attachment` signs
  `response-content-disposition` into the URL itself.
- **Text is served through `GET /api/nodes/<id>/text`, not fetched from the
  presigned URL.** A cross-origin `fetch` to S3 would need a `GET` in the
  bucket's CORS rule, and the decision is no: one authenticated same-origin
  request beats widening a rule whose allowed origins would then have to agree
  with the four places the API's already do. **The bucket's CORS rule is one
  line**: `PUT`, `content-type` + `content-length`, no exposed headers. It
  exists because the *upload* is a cross-origin PUT the browser preflights, and
  without it every upload fails with no status attached. Reads need nothing:
  the app draws media with `<img src>` and `<video src>`, and plain media
  loading is not subject to CORS.
- **The upload PUT is `XMLHttpRequest`, and it is the only request in the SPA
  that is not `fetch`.** `fetch` cannot report upload progress — its `Response`
  is the *download*, and streaming a request body to count it yourself needs
  `duplex: "half"` over HTTP/2, which Safari does not do. A 300 MB clip going out
  over a phone connection behind an indeterminate bar is indistinguishable from
  a frozen tab, so `upload.onprogress` is the feature rather than a nicety. See
  `frontend/src/apis/upload.ts`.
- **`Content-Length` is signed and the browser will not let script send it.** It
  is a forbidden header name: `setRequestHeader` for it is a silent no-op, and
  the browser computes the value from the body. The signature validates because
  that computed value *is* `file.size`, which is the number `upload-url` was
  asked to sign — agreement, not transmission. The uploader skips it explicitly
  rather than calling a no-op a reader would take for a working line.
- **iOS hands over HEIC, and studio refuses it with a message.** `.heic` is not
  in `keys.IMAGE_EXTENSIONS`, so an accepted one would be classified `other`,
  drawn as a file row rather than a tile, and displayable in no browser but
  Safari. The refusal happens before the node is created and names the fix
  (Settings › Camera › Formats › Most Compatible). Before adding the extension
  instead, note that Chrome cannot decode HEIC, so a tile would render as a
  broken image rather than a photo.
- **Every card, row and tile is itself a `<button>`, so a second control cannot
  go inside one.** A button nested in a button is invalid HTML that browsers
  resolve by dropping one of them — and the design system's `Checkbox.Root` is
  a `role="checkbox"` button, so it counts, and so is `Dropdown.Trigger`.
  `ItemActions` and the tile's checkbox are therefore always *siblings* of the
  opening button, positioned over it (`MediaTile`) or beside it (`FileRow`,
  `FolderCard`) — which is why those three carry their frame on a wrapper
  `<div>` rather than on the button. Anything else that lands in a listing has
  to be built the same way. Its feedback is inline because a toast portalled
  to `<body>` is not painted while an element is in native fullscreen — which
  the object screen's player can be.
- **A row's actions live in one `⋯` menu; the object screen names its own.**
  `ItemActions` uses `Dropdown`, absolutely positioned inside its own relative
  wrapper, and collapses four icons that would otherwise sit on every row. The
  object screen has one file and room to name what can be done to it, so
  `ObjectActions` spells them out.
- **A portal CAN paint inside fullscreen.** `Dialog`, `Drawer` and
  `AlertDialog` take a `container`; hand them the element that is fullscreen
  and the whole dialog mounts inside it instead of on `<body>`. `MediaPlayer`
  reports its own container through `onContainerChange` — from the ref
  callback, not from state, because the dialog parts read the target WHILE
  RENDERING and a ref filled by the same commit is still `null` then.
  `ObjectPage` holds it in state and passes it down. Keep `transform`,
  `filter`, `contain` and `will-change` off that element: any of them makes it
  the containing block for the popup's `position: fixed` and moves it.
- **Rename in a listing is `RenameForm`, driven by the row.** Rows render it
  `basis-full` on a wrapped line — a parent that knows a rename is open is what
  makes the field typeable. Keep it that way.
- **The media grid has a selection mode, and it changes what a press means.**
  Once anything is selected (`useSelection`), pressing a tile extends the
  selection instead of opening it — the photo-library bargain, and the only way
  to pick forty tiles on a touch screen without hunting forty checkboxes.
  Escape clears, but only when no overlay is open, because the object screen,
  the text page and the move picker each bind Escape to their own close — and
  the picker is often open *on* the selection, so clearing it there would be
  Escape cancelling a move by emptying what was being moved. Selection is keyed
  by node id rather than by grid index: a listing can be re-fetched underneath
  one — every write does exactly that — and an index-keyed selection would
  quietly come to mean different files.
- **The URL names a node by id, and CloudFront has to be in on it.**
  `/f/<node_id>` is a folder and `/o/<node_id>` is one file, open; `/` is the
  library root, whose id nothing knows before the first request.
  `utils/location` is the whole of that mapping. A node id is the one thing
  about a node that never changes, so a share link outlives both a rename and a
  move.
  - **Do not simplify the viewer-request function to extension matching.**
    `modules/hosting` routes by **location** (`/assets/…` and `/index.html`
    pass through, everything else rewrites to `index.html`) rather than by
    "does this look like a file", so an id URL and a URL ending in `.mp4` both
    reach the SPA without a wasted origin round trip through the 403/404
    fallbacks.
- **An object URL names the file, not its folder, so the folder is asked for.**
  `hooks/useFolder` reads `parent_id` off `GET /api/nodes/<id>` — but only when
  the listing already in hand does not hold the file. That keeps a walk through
  forty clips at zero requests: the object screen rewrites the URL to each one,
  and every one is in the listing. A cold share link asks once. Keeping the
  last folder instead would be wrong — going back into an object URL after
  browsing elsewhere would keep a folder the file is not in.
- **Names and paths come off the breadcrumbs.** The folder's own name, its
  parent and whether it is the root are read from the trail `GET /api/nodes`
  returns, which the server built by walking `parent_id`. Rebuilding any of it
  client-side would be a second, guessing implementation.
- **A full-screen box is sized in `dvh`, never `inset-0`.** `index.html` asks
  for `viewport-fit=cover`, so a `fixed` element pinned to all four sides is
  laid out against the *large* viewport — the one with the browser's toolbars
  hidden — and mobile Safari then draws its bottom toolbar over the result.
  `MediaPlayer`'s fullscreen shell is `height: 100dvh; max-height: 100dvh` and
  its two chrome rows carry `env(safe-area-inset-*)` padding — only while it
  owns the screen, because a landscape iPhone reports a 44px left inset that
  would be nonsense inside a 300px player nowhere near a bezel. **Sound is in
  the top row, not the bottom one**: the bottom edge is where a browser puts
  its own chrome, so keep controls you press *while a clip is playing* out of
  it.
- **Do not "fix" the mobile focus-zoom with `maximum-scale` in the viewport
  meta.** That disables pinch-zoom, which is a WCAG 1.4.4 failure. The fix is
  16px inputs and it is upstream in the design system.
- **Unmuting has to happen inside the click, not in an effect afterwards.**
  `useMediaPlayback.toggleMuted` sets `video.muted` on the element synchronously
  and lets React state follow. A passive effect is a later task, and Safari
  grants sound only within the gesture's own turn of the event loop. A refused
  `play()` is caught, not swallowed: playback falls back to muted and `blocked`
  is raised so the UI can say why. Check `volume` too, since a muted element
  sitting at `volume === 0` is still silent after unmuting.
- **`/o/<id>` is a page, not an overlay.** `ObjectPage` sits inside
  `AppLayout`, with a `PageBar`, one `MediaPlayer` in the content column, the
  file's own words beside it, and the neighbours as a horizontal filmstrip. A
  stage mounts one `<video>`. `useKeyboardNav` is Left/Right between files,
  plus Space, `m`, `f` and Esc. The seek bar is a `Slider`, which answers the
  arrow keys natively, and the hook ignores anything targeting an INPUT — so
  Left/Right scrub while the bar has focus and step between files when it does
  not. Space, `m` and `f` reach the player through `MediaPlayer`'s
  `onControlsChange`, because all three sit behind state the player owns and
  pressing them by finding a button's `aria-label` would make those labels an
  API.
- **The feed's cursor is an offset.** `reel_items` enumerates *rows* — a
  `by-recent` query from the library root, a `by-path` `begins_with` from
  anywhere else — bounded by `STUDIO_MAX_FOLDER_OBJECTS`. **It is
  fetch-then-sort**, because sorting by date means the whole branch must be
  known before a page can be cut from it and `name` is not an order either
  index offers. Presigning happens *after* the slice — one page's worth of
  URLs, never the branch's. Keep it that way. The bound **truncates** rather
  than refusing, and says so in `truncated`; `ObjectPage` renders the count
  with a `+` — `12 of 2000+` — because the alternative is a feed that silently
  claims the library ends where the cap did.
- **One picker, two verbs.** `DestinationPicker` serves both move and copy,
  because "browse to a folder and press the button" is the same interaction
  either way and a typed prefix is useless against folder names that are
  timestamps. `verb` rides on the picker's target state, so there is no way to
  have one open with no operation chosen. The single behavioural difference: a
  move into the folder the items are already in is disabled as a no-op, while
  a **copy** into it stays enabled, because that is how a file is duplicated
  and the server numbers the second one. Folders get `Move…` only — there is no
  folder-copy endpoint — which is why `ItemActions` takes `onCopyTo` as
  optional.
- **Every write re-fetches the listing rather than patching state.** A rename
  changes an item's position under `newest` and certainly under `name`;
  replaying that into a sorted array correctly is more code than one request,
  and code that would be wrong exactly where nobody tests. Exceptions: the
  recursive feed drops a deleted item locally (`dropItem`) because re-walking
  would shift every already-loaded page under the scroll position; a
  **folder** move does not clear the selection because there was none; and
  deleting the folder you are *in* skips the refresh because the folder it
  would refresh has just stopped existing — going up is what re-fetches.
- **The folder you are in is deleted from the action row, not from a menu.**
  Every other folder carries its own `Move…`/`Delete` in an `ItemActions` menu
  on its card — but that card is drawn by the folder's *parent*, so the one
  folder with no card on screen is the one you are standing in. `BrowsePage`
  puts a `ConfirmDeleteButton` (tone `icon`) in the action row, disabled at the
  root where the API refuses it anyway. Leaving is the one navigation between
  folders that **replaces** rather than pushes: the entry behind you would
  otherwise be the folder you just destroyed.
- **The three folder icons are one cluster.** Copy, delete this folder and new
  folder all act on the folder you are in, so they sit together at a tighter
  gap than the row's own. Upload sits on the far side of a `w-px` divider, and
  the destructive icon stays in the middle of the cluster — a delete flush
  against the one control a person arrives *looking* for is a mis-click with
  no undo. *Where you are* on top, everything you can *do* below.
- **The browser has two views, and Media is a SEARCH.** `Folders | Media` in
  the action row. Media sends `kind=image,video` with `depth=all` — the same
  trick the tag filter uses. Folders and text are not hidden by a branch in the
  render; they are not in the answer, and the two sections that draw them render
  nothing on their own. It composes with everything already
  there: the folder chips still say *where*, the tag filter still narrows
  *what*, and sort, filter, selection, upload and every bulk write work
  unchanged over the flat result. `?view=media`, so it is a link.
- **A project's Runs tab is NOT a browser scoped to `runs/`.** It was, with a
  `List | Grid` toggle; Grid drew the file browser over the `runs/` folder in
  Media view, which is a run's OUTPUTS — Files' question, one tab over, on
  exactly the same folder. The Runs tab is the feed (above), whose unit is the
  RUN. A project draws one browser now, so `view`/`folder` are its only
  browser keys.
- **A deep listing addresses its tiles `in=recursive:`.** `?in=f:<folder>`
  makes the viewer re-read that folder one level down to find the neighbours,
  which is right for a readdir and wrong for both listings that search the
  branch — Media view and the tag filter. `FolderBrowser` reads `data.depth` —
  what the server says it did — and hands it to `openFile` / `fileHref`. The
  viewer does not adopt `items[0]` for an id it has not reached: a paged walk
  that has not found the file yet is still searching rather than holding a dead
  link.
- **There is no "Play reel" button, no Identity tab and no Inputs tab.** Each
  would be a second way of looking at a listing the page already shows.
  Identity is a *tag* (`default`), so it is a preset of the Files tab; Inputs
  is a project's `input/` folder, drawn one tab over from the Files that already
  holds it — `--input N` is a position in a name-ascending listing that nothing
  stores, and `studio projects inputs <project>` prints those positions. The
  viewer still plays a feed: opening any tile from the library's Media view
  scrolls the recursive walk (`/o/<id>?in=recursive`). Home lists no media —
  it is characters and projects, and the Recent grid it used to carry walked
  the whole library for twelve tiles.
- **Destructive confirmation for ONE file is in the button, not in a dialog.**
  `ConfirmDeleteButton` arms on the first press, names what it will destroy,
  and disarms on a timeout, on blur, or on Escape — a dialog in a fixed
  position trains a second click that lands before anyone reads it. A
  **cascade** is a different bargain and gets `ConfirmDestroyDialog`, where the
  word has to be typed.
- **No query string becomes an S3 key.** `GET /api/asset` takes `?node=` and
  `?disposition=`. Every route takes a node id, an entity id, or (for
  `GET /api/resolve`) a name path looked up segment by segment as exact `NAME#`
  sort keys; `clean_name` refuses a slash, a `.`, a `..` and a control
  character on the way *in*, so `../elsewhere` is a name nothing is called
  rather than traversal to reject. `keys.py` is `clean_name` and the extension
  tables.
- **The Lambda's env vars come from the deploy workflow, not from Terraform.**
  `lifecycle { ignore_changes = [environment] }` means the `environment` block
  in `modules/compute` only applies the first time the function is created;
  after that the `jq` block in `studio-prod.yaml`'s `update-lambda` job is the
  only thing that sets the API function's environment — **all eight of it**:
  `STUDIO_MEDIA_BUCKET`, `STUDIO_ALLOWED_ORIGIN`, `STUDIO_CATALOG_TABLE`,
  `STUDIO_COGNITO_USER_POOL_ID`, `STUDIO_COGNITO_CLIENT_ID`,
  `STUDIO_WEBHOOK_BASE_URL`, `STUDIO_RENDER_QUEUE_URL`,
  `STUDIO_REPLICATE_TOKEN_PARAMETER`. `--environment` **replaces** the map
  rather than merging into it, so that document has to be complete: dropping a
  line unsets the variable on the next deploy, and a variable added to
  `modules/compute` and not here reads as its default in the running function
  behind a clean plan. `STUDIO_REPLICATE_TOKEN_PARAMETER` is a parameter
  *name*, never a token. An unset `STUDIO_CATALOG_TABLE` is the difference
  between a browsable library and an empty one.
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
- **`@ansavva/design-system` is pinned exactly (0.16.0).** `0.x` caret ranges do
  not pick up minors. Read the package's `CHANGELOG.md` before bumping.
- **React 19**, matching `website/frontend` and `humbugg/marketing`. The design
  system's source uses React 19 DOM props (`inert`, `onScrollEnd`), so React 18
  types fail `tsc` inside `node_modules`.
- **A `<video>` gets no `src` until its box is near the viewport.** The object
  screen mounts one, and the grids use `useNearViewport` — which is what stops
  sixty range requests on a folder of sixty clips, while `preload="metadata"`
  is how a poster frame arrives free out of a bucket that ships no derivatives.
  Ref callbacks are memoised per key in `useMediaPlayback.register`: an inline
  arrow is a new identity every render, which would detach and re-attach the
  element on every tick of the scrub bar.
- **A date sort has no tie-break, and should not get one.** `catalog._now`
  stamps microseconds, so `_sort_records` is one pass and equal timestamps mean
  equal *instants*. Python's stable sort leaves those in the order the query
  returned them. Do not reintroduce a secondary key to "make it deterministic"
  — the thing it would sort on is `blob_key`, which is opaque and which a
  rename does not change.
- **A listing sorts on one date and shows that same date.** `_timestamp`
  returns `updated_at`, falling back to `created_at` only for a row old enough
  to predate the pair. A listing ordered by a date it does not display reads as
  a bug forever, which is why there is one accessor rather than two fields.
- Lambda uses `lifecycle { ignore_changes = [image_uri, environment] }`; the
  deploy workflow owns the image tag and the env vars.

### UI vocabulary

A fixed set of primitives, not freehand markup, is what a screen is built
from: `PageBar` (title, meta, actions, a `⋯` menu) and `FormBar` (a form's
save/cancel row); `EmptyState` and `LoadError` for the two ways a listing has
nothing to show; `PageLoading`/`SectionLoading` for the two loading weights;
`EntityRow`/`EntityCard`/`MediaTile` for a listing item; `FilterBar` for the
tag/search strip above one; `ConfirmDeleteButton`/`ConfirmDestroyDialog` for destructive
actions, weighted by what is lost — one entity arms in place, anything with
children types its name; `useArmed`, the arm/disarm machine both of those (and
`ArmedButton`, `ItemActions`) run on; and toasts (`useToast`) for feedback that
is not a page's own error state.

**Two of these used to be local and are the package's now** (design-system
0.17.0): `Chip`/`chipClass` for the square bordered toggle, and — replacing a
`dangerButtonClass` helper that re-derived the fill — `Button intent="danger"`
with `wrap` for a label that is a sentence. Reach for the package's.

Nine rules keep every screen speaking that vocabulary, #589-#596:

1. **Square corners** — `rounded-none`; `rounded-pill` stays a shape, not a corner.
2. **No ghost intent** — `secondary` is `Button`'s quiet weight.
3. **Semantic colour only** — no raw `neutral-*` ramp class. A control drawn
   over MEDIA uses the package's `overlay-*` roles (`IconButton
   intent="overlay"` wears them); those replaced a `--color-chrome-*` set
   `styles/app.css` used to define here.
4. **No hand-rolled controls** — `Button`/`IconButton`/`buttonClass`, not a
   `<button className="…border…hover:…">`.
5. **No literal glyph characters** — icons are SVGs from `components/common/icons.tsx`.
6. **Every spinner says what it is loading** — `ApertureSpinner` takes a `label`.
7. **Empty-state prose lives in `EmptyState`** — nothing else says "No … yet."
8. **One shape for a failure title** — "Could not ‹verb› ‹noun›", never "That
   did not…"/"Nothing was…".
9. **The lint rules are what keep the other eight true, not memory.** This
   directory's `eslint/` (a local plugin, no dependency added) enforces 1, 3
   and 5 by walking every class-bearing expression — a JSX `className`, a
   template literal, a hoisted constant, or an argument to
   `buttonClass`/`chipClass`/`clsx`/`twMerge` all resolve to the same check —
   and 4 the same way over `<button>` elements outside `components/common/`;
   2, 6, 7 and 8 are `no-restricted-syntax` selectors in `eslint.config.js`.
   `npm run lint` is what a PR runs.

## API

Every route is behind the Cognito authorizer except `GET /api/health`.

**Every other route is about exactly one library, and `before_request` decides
which — once.** Three cases, in order: the `X-Studio-Library` header if it names
a library the caller is a member of (403 otherwise); a sole membership if there
is exactly one; a refusal. No header and no memberships is a **403**, not the
400 the ambiguous case gets, because there is no header that caller could send
that would work — the remedy is provisioning, not a retry. No header and several
memberships is a 400 naming them, so it is answerable from `curl` without a
second round trip. Nothing downstream re-derives any of this.

`X-Studio-Library` is a custom request header, so it is subject to the same
four-file agreement the write verbs are (`app_factory`'s `CORS(...)`, the MOCK
preflight, and both gateway responses in `modules/api_gateway`). Missing from
any of them, the SPA sees a network error with no status attached — the one
failure mode in this service that carries no message at all.

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
adds it here on purpose. The S3 key stays internal because it is *meaningless*
— correct forever only for as long as nothing outside `services.catalog` parses
one. `path` is withheld too: it is a materialised index of ancestor ids that a
move rebuilds, and `parent_id` answers the same question authoritatively.

**Every node response is membership-checked against the node's own `lib`**, not
against the library the request claimed. A node id is a v4 UUID, so this is not
a guard against guessing; it is the guard against a *shared* id once a library
has more than one member. A node that does not exist is 404 before that check
can run.

**`GET /api/nodes` is the one listing.** Depth, kind, tag and paging are
arguments. It is one query plus `ceil(n / 100)` batched reads, and that is the
shape to keep: the by-parent item carries the index projection only
(`node_id, lib, kind, path, created_at`), so `size` and `content_type` come from
a `BatchGetItem` over the `META` rows. Widening the projection would put a
mutable copy of every file's metadata on a second item, which every rename and
every text edit would then have to keep in step. `UnprocessedKeys` comes back on
a **200**, so botocore's retries never see it — `catalog.records` retries it
explicitly and raises rather than answering with a short listing.

**One addressing scheme.** Every route takes a **node id**, or an entity id
where the resource is an entity. `GET /api/resolve?path=` is the single
translation from a slash-joined name path into the id everything else wants. An
entity's name is free text and two may share one, so no route resolves a name;
the CLI matches a name over a listing and refuses an ambiguous one with the
ids. A name path's FIRST segment is an entity's root folder, which is named by
the entity's id.

| Route | Returns |
|---|---|
| `GET /api/health` | `{"status": "ok"}` — liveness, touches neither store |
| `GET /api/libraries` | `[{id, name, role}]` — the caller's libraries. Authenticated, **not** library-scoped |
| `GET /api/nodes?under=&depth=&kind=&tag=&sort=&cursor=&limit=` | **The one listing.** Everything under a node — `depth=1` (default) for a folder, `depth=all` for the branch; `kind=` and `tag=` filter; paged. One `entries` array discriminated by `kind`, plus `breadcrumbs`, per-kind `counts`, `total`, `truncated`, `next_cursor`. Omit `under` for the library root |
| `GET /api/nodes/<id>` | One node. 404 unknown id, 403 another library |
| `GET /api/nodes/<id>/owner` | Which entity a node belongs to, derived from its ancestry — `{kind, id, name}` or null |
| `GET /api/resolve?path=` | A slash-joined name path → the node it names. An empty path is the library root |
| `POST /api/nodes` | `{parent, name, kind, blob_key?, size?, content_type?, on_conflict?}` → creates a folder or a file. **201.** 409 if the name is taken, unless `on_conflict: "number"` |
| `PATCH /api/nodes/<id>` | `{name}` to rename **or** `{parent}` to move — both at once is a 400, not a guess. `{description, tags}` → what a picture IS and what it is FOR |
| `DELETE /api/nodes/<id>` | Node and subtree. Rows first, then blobs |
| `POST /api/nodes/move` | `{ids: [...], destination}` → moves 1..N nodes, names kept. 409 if taken |
| `POST /api/nodes/copy` | `{ids: [...], destination}` → copies 1..N nodes, sources kept. Names numbered if taken |
| `DELETE /api/nodes` | `{ids: [...]}` → deletes 1..N nodes and their subtrees. Rows first, then blobs |
| `GET /api/nodes/<id>/text` | A `.json` / `.md` / `.txt` node's contents, capped at 1 MB |
| `PATCH /api/nodes/<id>/text` | `{content}` → overwrites a text node's bytes and restamps its row |
| `GET /api/nodes/<id>/download-url` | A fresh presigned GET for the node's blob. `disposition=attachment` to download |
| `POST /api/nodes/<id>/upload-url` | `{size, content_type}` → a presigned PUT for `blobs/<id>`. Signed length and type |
| `POST /api/nodes/<id>/confirm-upload` | `HeadObject`s the blob and writes `size`/`content_type` onto the row |
| `GET /api/asset?node=&disposition=` | A fresh presigned URL for one node's bytes — what the SPA calls on an expired tile |

### The entity routes

| Route | Returns |
|---|---|
| `GET \| POST /api/characters` | List, or create — record, library index row, root folder and the starting pools in one transaction. **No 409**: a name is a label, so nothing here can collide |
| `GET \| PATCH \| DELETE /api/characters/<id>` | One character, addressed by id. `PATCH` carries `rev` and **409**s if it has moved |
| `PATCH /api/characters/<id>/profile` | `{profile, rev}` — the bible, validated |
| `GET /api/characters/<id>/selection` | `?pick=&tag=&limit=` → the ordered nodes a model would be shown. **Refuses** an over-cap selection with the index in the body |
| `GET /api/characters/<id>/textblock` · `/runs` · `/projects` | The identity paragraph; the runs that used it; the projects that involve it |
| `GET \| POST /api/projects` | List, or create |
| `GET \| PATCH \| DELETE /api/projects/<id>` | One project, `rev`-guarded like a character |
| `PATCH /api/projects/<id>/characters` | `{characters: [...]}` → replaces the involvement links |
| `GET /api/projects/<id>/inputs` · `/runs` · `/scenes` · `/movies` | The working pool, and the three tiers |
| `GET \| POST /api/runs` | Query by `project`, `character`, `status`, `model`, `kind`, `since`, `fingerprint`, `q`; or create a draft. **Refuses a URL-shaped binding.** `?view=feed` expands each row for the feed — see below |
| `GET /api/runs/resolve` | A run by `ref` |
| `GET \| PATCH \| DELETE /api/runs/<id>` | The envelope, with outputs and bindings expanded |
| `GET /api/runs/<id>/payload` · `POST /api/runs/<id>/plan/preview` | The payload a submit would send, assembled from the plan |
| `PATCH /api/runs/<id>/plan` · `PATCH /api/runs/<id>/sends` | Replace half the plan; each moves the fingerprint. Refused once submitted |
| `POST /api/runs/<id>/submit` | **Sends a draft to the provider.** The one route in this service that spends money; calling it is the decision — there is no approve step |
| `POST /api/runs/<id>/reconcile` | Asks the provider what happened and closes the run — for a callback that never arrived |
| `POST /api/runs/<id>/outputs` · `/response` | An upload URL per output; the provider's response stored as a payload blob |
| `GET \| POST /api/scenes` · `GET \| PATCH \| DELETE /api/scenes/<id>` | The scene record |
| `PATCH /api/scenes/<id>/shots` · `/shots/<shot_id>` | The plan: revise it, or change one shot |
| `POST /api/scenes/<id>/output` · `POST /api/movies/<id>/output` | Upload URL for a cut made elsewhere. The render path does not use it |
| `POST /api/renders` · `GET /api/renders/<id>` | **Enqueue an encode, and poll the row.** A stitch, a frame grab, a contact grid or a contact sheet, done by a second container image with `ffmpeg` in it |
| `POST /api/images/convert` · `/api/images/crop` | The two image operations that are **not** on that queue — sub-second, so synchronous, with Pillow and no ffmpeg |
| `GET \| POST /api/movies` · `GET \| PATCH \| DELETE /api/movies/<id>` · `PATCH /api/movies/<id>/scenes` | The tier above |
| `GET /api/models` · `GET /api/models/<name>` · `/schema` · `/readme` | The model registry |
| `GET /api/templates` · `PATCH \| DELETE /api/templates/<id>` · `PATCH \| DELETE /api/templates/blocks/<name>` | The template library |
| `GET /api/tags` · `PATCH \| DELETE /api/tags/<name>` | The tag vocabulary |
| `GET \| POST /api/phrasebook` · `DELETE /api/phrasebook/<model>/<avoid>` | The wording lists, as `TERM#` rows |
| `POST /api/prompt` | Checks a structured video prompt |

**`GET /api/runs` answers two shapes, and the wider one is opt-in.** A listing
row is the projection the `PROJ#<id>` / `RUN#<created>#<id>` item carries —
`id, project, status, kind, model, created, cost, thumb, fingerprint?` — and
every consumer of it is cheap *because* it reads no envelope: the runs grid,
the CLI's `runs list`, and the duplicate-submission check (`?fingerprint=`,
one query). The feed is the one screen that wants the whole run per row
without a fetch per row, so it asks with **`?view=feed`** and each row becomes:

```jsonc
{
  "id": "run-…", "lib": "lib-…", "project": "proj-…",
  "status": "running", "kind": "image",
  "engine": "studio-media-gpt-image-2", "model": "openai/gpt-image-2",
  "created": "…", "updated": "…", "submitted": "…", "completed": null,
  "cost": { "currency": null, "amount": null, "predict_time": 98.2 },
  "error": null, "fingerprint": "sha256:…",          // present or absent, like the listing row — never null
  "plan": { "version": 1, "origin": "authored", "prompt": "…", "params": { "aspect_ratio": "3:4" } },
  "characters": ["char-…"],
  "cast": [{ "id": "char-…", "name": "<name>" }],
  "sends":   [{ "order": 1, "field": "input_images", "role": "reference",
                "source": { "kind": "character", "character": "char-…" },
                "node": "node-…", "name": "seed-01.jpg", "size": 167810,
                "content_type": "image/jpeg", "url": "https://…presigned" }],
  "outputs": [{ "node": "node-…", "name": "frame.png", "size": 2172168,
                "content_type": "image/png", "url": "https://…presigned" }],
  "thumb": { "node": "node-…", "url": "https://…presigned" }
}
```

An allowlist, like every view here: no `approval`, no `plan_digest`, no
`stale` — those were the deleted run page's. `cast` is what `GET /api/runs/<id>`
answers as ids, named: the record's own `characters`, else the owners of what
it bound, read off the sends' recorded provenance rather than by walking each
node's ancestry. `?character=` answers with envelopes and `?project=` with
rows; the feed projects both to this one shape. A page costs one batched read
for the envelopes, **one query per run for its sends**, one batched read over
every node the page points at and one for the cast's names; signing is local
(~0.04 ms a URL, measured) and is not what bounds the page —
`STUDIO_MAX_FEED_ROWS` is.

**`?q=<text>` is a prompt search, and the catalog has no text index.** It
matches the plan's prompt case-insensitively as a substring — the string
leaves of a structured prompt, never its keys, so `camera` does not match
every video prompt ever written — within whatever `project` / `character` /
library scope and cheap filters (`status`, `model`, `kind`, `since`,
`include=drafts`) the request names. It reads envelopes to do it, so one call
scans at most `STUDIO_MAX_SEARCH_SCAN` rows past the cursor and hands back
what matched: **a page may come back shorter than `limit`, or empty, with
`cursor` still set, and that means "keep going"**. The cursor always advances,
so a query matching nothing ends in `ceil(runs / scan)` calls rather than one
call reading the project. Composes with `view=feed`, which reuses the
envelopes the search read.

**Everything above is `PATCH` where a REST habit would reach for `PUT`**,
including the whole-document writes (`/profile`, `/shots`, `/text`). `PUT` is
not in the CORS method list, that list lives in four files that have to agree,
and `PATCH` is already in all four. Adding `PUT` properly is a four-file change
nobody has needed yet.

**Rename and move are separate operations and must stay separate.** A rename
takes a `name` and changes the last segment; a move takes a destination folder
and changes the parent. `keys.clean_name` refuses a slash, so a rename cannot
become a move by punctuation, and a destination is always read as a folder, so
a move cannot become a rename by typing a filename into it — a request naming
no existing folder is a 404. `PATCH /api/nodes/<id>` refuses `name` and
`parent` together: the two orderings give different answers when the
destination already holds that name, and choosing one silently is how a file
ends up somewhere nobody looks for it.

**A conflict is a transaction condition failure, not a listing.** Every create,
rename and move puts its `NAME#` item under `attribute_not_exists(pk)` and turns
the cancelled transaction into a 409. A bulk move still pre-checks every
destination with a read, because each file is its own transaction and a
conflict found on the eighth would leave seven already moved — that read is a
courtesy, and the condition expression is the guarantee.

**`POST /api/nodes/copy` is `move` minus the delete, plus numbering.** Same
body, same bulk cap. A name the destination already holds is numbered, never
refused: `clip.mp4` lands as `clip (2).mp4`. A move refuses the whole request
on a conflict because a half-done move splits a selection across two folders;
a copy has no such split. Numbering looks at names only — it does not compare
sizes to decide that an identical file is "already there" and skip it. Ask for
a copy, get a copy. A folder copies as one of the `ids` like anything else, but
a *deep* copy is not on offer: a subtree copy can be arbitrarily large with no
progress to report, and nothing has wanted one yet.

`sort` is one of `newest` (default), `oldest`, `name`, `name_desc`.

The write routes carry a JSON body, `DELETE /api/nodes` included. That is
unusual but well-defined, and API Gateway's Lambda proxy passes it through
intact; the alternative for a grid selection is a few hundred repeated query
parameters, which is a URL length limit waiting to happen on exactly the case
bulk delete exists for.

**Four places have to agree on the allowed methods**, because a browser's
preflight is answered by API Gateway rather than by Flask: `CORS(methods=...)`
in `app_factory.py`, the MOCK integration response in `modules/api_gateway`,
and the `UNAUTHORIZED` and `ACCESS_DENIED` gateway responses beside it. A verb
missing from any of them is a CORS failure no Flask configuration can rescue.
`backend/tests/unit/test_cors_agreement.py` pins it.

### Limits

| Env var | Default | Guards |
|---|---|---|
| `STUDIO_MAX_BULK_KEYS` | 1000 | One `DeleteObjects` round trip |
| `STUDIO_MAX_FOLDER_OBJECTS` | 2000 | A subtree operation the Lambda can finish — **and the feed's enumeration** |
| `STUDIO_MAX_TEXT_BYTES` | 1 MiB | What `GET /api/nodes/<id>/text` will read and `PATCH` will write |
| `STUDIO_MAX_UPLOAD_BYTES` | 5 GiB | S3's single-PUT ceiling, declared at signing time |
| `STUDIO_PRESIGN_TTL_SECONDS` | 900 | A read URL's requested life |
| `STUDIO_UPLOAD_TTL_SECONDS` | 300 | An upload URL's — deliberately shorter |
| `STUDIO_MAX_FEED_ROWS` | 50 | One `GET /api/runs?view=feed` page. A larger `limit` is **clamped**, and `cursor` says so |
| `STUDIO_MAX_SEARCH_SCAN` | 200 | How many runs one `GET /api/runs?q=` call reads looking for a match. Bounds the call, not the answer — the cursor carries on |

`STUDIO_MAX_FOLDER_OBJECTS` means two different things, deliberately. For a
**subtree operation** it is a **refusal** — an operation that stopped halfway
would leave no record of which half moved. For the **feed** it **truncates**,
and says so in `truncated`, because a page of a library is allowed to be
shorter than the library.

## Local development

**A per-machine dev stack comes first, and `dev-up.sh` refuses to start without
one.** The stack is this machine's own Cognito pool, media bucket and catalog
table, named `studio-dev-<short12>-*` from a persistent UUID in
`~/.config/andreas-services/studio/machine-id`. Failing early is deliberate: an
API with no pool 500s on every call, which is a slower way to learn the same
thing.

```bash
aws sts get-caller-identity                          # confirm the access key resolves
./studio/scripts/dev-aws-setup.sh                    # once per machine
./studio/scripts/dev-user.sh --generate-password     # its one test account
```

```bash
# Both surfaces together (backend :8000, frontend :5173).
./studio/scripts/dev-up.sh
```

Or separately:

```bash
cd studio/backend
poetry install --no-root
poetry run python -m studio_core.handlers.local.api.api_dev_server
poetry run pytest                                          # moto-backed, no AWS needed

cd studio/frontend
export NODE_AUTH_TOKEN=$(gh auth token)                    # needs read:packages
npm ci && npm run dev
npm test                                                   # vitest, no AWS needed
```

`aws sts get-caller-identity` is a trustworthy probe: the CLI, boto3 and the
Terraform provider all read the same access key.

`dev-setup.sh` writes `frontend/.env.local` **from this machine's dev stack's
Terraform outputs**, syncs the `dev` profile, and installs
`frontend/node_modules` — do not hand-copy the example or hand-edit the result;
the generated file says as much in its own header. Without the env file the app
shows "Auth is not configured"; without node_modules every local binary is
missing, and the first one you hit is `tsc: not found`.

The script runs from the SessionStart hook and **tolerates a missing stack**,
warning and carrying on — it still has a toolchain to install. It also warns
loudly, rather than rewriting, about a `studio/.env` that pins a prod bucket.
The file is the developer's; silently repointing where their commands write is
worse than telling them.

## Testing

`backend/tests/unit/` is moto-backed pytest over a miniature of the catalog
table and the bucket, and covers the whole read and write surface. It is moto
and not a real stack on purpose: the dev stack costs an apply, and a suite that
needs AWS is a suite that stops being run.

`frontend/src/**/*.test.ts(x)` is `vitest` + `@testing-library/react` + `jsdom`,
`npm test`, run in `studio-pr.yml` beside lint and typecheck. The bar for a
frontend test is a failure the app cannot report on its own — a wrong header, a
wrong argument that typechecks, a confirm that fires after a failed PUT — never
a blank page, which `lint → typecheck → build` already catches. What is
covered: the route table (`routes.test.tsx`), the id↔URL mapping
(`utils/location.test.ts`), the API client's library header
(`apis/client.test.ts`), node addressing (`apis/studio.test.ts`,
`components/NodeAddressing.test.tsx`), the upload sequence
(`apis/upload.test.ts`), the run surface (`components/run/*.test.tsx`,
`components/project/RunFeed.test.tsx`, `components/run/RunLightbox.test.tsx`), the player (`components/media/*.test.tsx`,
`hooks/useMediaPlayback.test.ts`), and the entity pages
(`pages/{Character,Project,Scene,Movie,Object,Templates}Page.test.tsx`).

Two things follow for anyone adding to this. The route table lives in
`routes.tsx` rather than `App.tsx` so it can be exercised without the auth
stack — the gate renders a "not configured" notice when no user pool is set,
which in a test is every URL resolving to the same thing. And `vite.config.ts`
sets both `clearMocks` and `restoreMocks`: "the resolver was not called" is one
of the assertions and is worthless against a tally shared with the previous
case.

Coverage is measured and gates on nothing (`npm run test:coverage`);
`vite.config.ts` makes the argument at length.

`frontend/e2e/` is Playwright over committed `/api/**` fixtures — see
[`../frontend/e2e/README.md`](../frontend/e2e/README.md).

### Two suites that do not run on a PR

`backend/tests/integration/` and `backend/tests/smoke/` are both skipped at
collection unless asked for by name — `STUDIO_INTEGRATION=1` and `STUDIO_SMOKE=1`
— because both write to a real AWS account. They exist because moto **does not
enforce IAM at all**: the whole backend suite passes against a policy granting
nothing.

They are not two copies of the same idea. The integration suite runs Flask
in-process against this machine's dev stack, under a developer's own
credentials, and settles what a fake cannot — a presigned URL that really
fetches, a real `TransactWriteItems` cancellation, a bucket byte-identical
either side of a move. **It never exercises the Lambda's execution role**, which
is far narrower than a developer's. The smoke suite is the one that does: it
signs in to the real pool and drives the deployed API over HTTPS, which is the
only way to find out whether the deployed function may make the calls the code
makes.

The smoke suite runs in `studio-prod.yaml` **after** the deploy, so it is a
detector and not a gate — studio has no staging. Its account is a member of
exactly one library and can reach nothing else, which is what confines it; see
[`../backend/tests/smoke/README.md`](../backend/tests/smoke/README.md) and
[`PROD_SMOKE.md`](PROD_SMOKE.md).

## Creating users

There is no sign-up. Accounts are created out of band, and **the two pools have
two scripts** — `create-user.sh` defaults `USER_POOL_ID` from SSM, which is the
**prod** pool, so it is not the one to reach for while developing:

```bash
STUDIO_EMAIL=you@example.com ./studio/scripts/create-user.sh   # prod pool
./studio/scripts/dev-user.sh --generate-password               # this machine's dev pool
```

Cognito emails a temporary password; signing in with it prompts for a new one.
Pass `STUDIO_PASSWORD` to set a permanent one directly instead — and note it
is *converged*: re-running with a new value resets the account's password,
which is how a studio password is reset. `--no-converge` opts out.

Pass `STUDIO_LIBRARY` and the script grants membership itself, by calling
`add-member.sh`. Without it the script warns, because an account with no
membership signs in successfully and sees nothing.

**A pool account is not access to anything.** Membership is a catalog row
(`USER#<sub>` / `LIB#<lib_id>`), and creating the Cognito user does not write
one — so a freshly created account signs in, renders, and gets a 403 from
`before_request` with "You are not a member of any library." That is the right
status: the pool is admin-create-only, so it is a provisioning gap rather than
anything the caller did wrong, and `GET /api/libraries` returning an empty 200
is how it gets diagnosed. **`scripts/add-member.sh` writes that row:**

```bash
STUDIO_EMAIL=you@example.com STUDIO_LIBRARY=lib-… ./studio/scripts/add-member.sh
STUDIO_LIBRARY=lib-… ./studio/scripts/add-member.sh --list
```

It reads the `sub` off the pool account rather than inventing one, is safe to
run repeatedly, and leaves an existing membership exactly as it is —
**including its role**, because "add" quietly demoting an owner is the kind of
surprise that costs somebody their library. `STUDIO_ROLE` is `member` by
default; no route reads the role, so `owner` records who holds the library
rather than granting anything wider.

Its defaults come from SSM, so they point at **prod**, like `create-user.sh`
and unlike everything named `dev-*`. Set `USER_POOL_ID` and `CATALOG_TABLE`
from `dev-aws-setup.sh`'s outputs to reach this machine's stack.

**Deliberately a script and not a route**: a route that granted membership
would be a route that could grant itself access to somebody else's library.

## Deployment

`.github/workflows/studio-prod.yaml` — `detect-changes → bootstrap-ecr →
build-and-push → deploy-infra → update-lambda + deploy-frontend`, with `smoke`
after `update-lambda` — a post-deploy detector, not a gate
([`PROD_SMOKE.md`](PROD_SMOKE.md)). The SPA is built in `deploy-frontend`
rather than earlier because Vite inlines every `VITE_*` value at build time and
the Cognito ids come out of the apply.

Terraform state: `s3://andreas-services-terraform-state/studio/prod/terraform.tfstate`.
