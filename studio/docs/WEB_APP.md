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
nothing outside `services/catalog.py` parses. That is the inversion this whole
document turns on: studio used to *be* a rendering of `ListObjectsV2`, and it is
now a rendering of a query. Nothing lists the bucket to find out what exists.

What that bought is what the old shape could not have: a rename that moves no
bytes, a share link that survives one, a library that can have more than one
member, and a `parent_id` that a folder can be reached through without a string
being cut on `/`. What it costs is that a lost row is a lost file even though
every byte of it survives — S3 versioning does not reach a row, and the table's
PITR is its only recovery. See [../infra/README.md](../infra/README.md).

The generation pipeline produces the media and records it through
`POST /api/runs`. Studio makes the result browsable: folders keep their
structure, images and video are the focus, and every item can be opened
fullscreen or flipped through as a vertical reel.

**Studio reads the library, tidies it, and now accepts bytes for it — it still
does not produce it.** It browses, and it can rename, move, copy, delete, create
folders, and edit the text files in place. **It can now also accept an upload**
(#294), through a presigned PUT that the bytes travel to directly. What it still
cannot do is *generate*: making media is the pipeline's job, and the pipeline
decides what to make and pays for it.

The boundary has widened twice, and this file has recorded each widening rather
than replacing the sentence. It began as "a reader and only a reader"; it became
a reader that tidies; it is now a reader that tidies and accepts. The reasoning
for each is in **What this service may do to the bucket** below — read it before
widening it a third time.

The line between "edit a text file" and "upload" is worth stating, because it is
thinner than it sounds and is held in exactly one place: `manage.update_text`
refuses a node that is not a file carrying a blob. That used to be `s3.exists` on
a key; #319 moved it onto the row without weakening it, and it now also refuses
the case the key-addressed form could not represent — a placeholder whose upload
never landed.

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
| Data | **DynamoDB, single-table** (`studio-prod-catalog`) — one item pair per node, three `ALL`-projected GSIs. No cache. Listings are a query. |
| Blobs | S3, addressed only by a row's opaque `blob_key`. Never listed. |
| Routing | By node id. `/f/<id>` is a folder, `/o/<id>` is one open file; a pre-#313 name path is resolved once and redirected. |
| Media | Presigned S3 GET URLs, direct from the browser to S3 |
| Infra | Terraform in `studio/infra/` (`modules/` + `envs/prod` + a per-machine `envs/dev`) |

Both of the first two rows used to read differently and the change is worth
naming rather than editing over. **Data** said "None. No DynamoDB, no cache —
listings come straight from S3 on each request", which was the design until
#309–#311. **Routing** said "the path *is* the S3 key", which was true until
#313 and is the reason share links written before it need a resolver at all: a
key changes when a file is renamed, so every link to a renamed clip broke. A
node id does not change, ever, which is the whole argument for both.

## Directory Structure

```
studio/
├── backend/                  # Flask + Dockerfile, shipped as a container Lambda
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── studio_core/          # routes → services → clients
│   │   ├── routes/           # nodes.py + libraries.py (the catalog's surface),
│   │   │                     #   browse.py (a folder ready to draw), manage.py (writes)
│   │   ├── services/         # catalog.py owns the item shapes; browse.py, manage.py,
│   │   │                     #   identity.py (JWT), keys.py (classification + confinement)
│   │   └── clients/aws/      # dynamodb.py, s3.py — the only boto3 in the service
│   └── tests/                # pytest + moto over a miniature of the table and the bucket
├── frontend/                 # Vite + React SPA (studio.andreas.services)
│   ├── index.html            # pins data-theme="dark"
│   └── src/                  # apis, components, pages, hooks, context, utils, types
│                             # routes.tsx is the URL table; *.test.tsx is vitest
├── infra/
│   ├── modules/              # auth, compute, api_gateway, api_domain, hosting,
│   │                         #   media, catalog, dev_storage
│   ├── envs/prod/            # applied by CI
│   └── envs/dev/             # per machine, applied only by scripts/dev-aws-*.sh
├── pipeline/                 # the generation half's code — local only, never deploys
├── scripts/                  # create-user.sh; dev-setup.sh / dev-up.sh;
│                             #   dev-aws-{setup,reset,destroy}.sh, dev-user.sh, dev-token.sh
├── .claude/skills/           # the generation half's docs — local only, never deploys
├── docs/
│   ├── PIPELINE.md           # the local half
│   └── WEB_APP.md            # ← this file
└── CLAUDE.md                 # the index over both
```

## What this service may do to the library

Two stores, and the interesting half of this section is that **only one of them
has a boundary IAM can describe.**

`studio-prod-media-us-east-1` is studio's own bucket, declared in
`infra/modules/media` and imported into `studio/prod` state in August 2026. It
did not used to be: it was provisioned from a separate repo, and this section
used to be titled *The media bucket is not ours* and forbade any resource or
data source for it. That is no longer the arrangement — see
[../infra/README.md](../infra/README.md). `studio-prod-catalog` is studio's own
table, declared in `infra/modules/catalog`, and has never been anything else.

What did **not** change is which side of the fence this API sits on. The
pipeline runs from a laptop under a human's own AWS login. This Lambda is the
only thing reachable from the internet, so it is still the thing worth scoping,
and everything below still applies to it.

### The S3 grant, which confines nothing

The Lambda role's policy (`modules/compute`) grants four actions:
`s3:ListBucket` (prefix-conditioned), `s3:GetObject`, `s3:PutObject` and
`s3:DeleteObject`. All four are scoped to `media_root_prefix`, **which is
empty** — see *What the library looks like* below — so in practice they cover
the whole bucket.

**That is a reversal of what this file used to say, and it was deliberate.** The
old rule was "do not add a write action; a feature that needs one belongs in the
pipeline". It changed because tidying is not a pipeline activity — you notice a
run produced nothing worth keeping while you are looking at it, and routing that
back through the pipeline meant it never happened. So renaming, deleting and
creating folders live here now.

The parts of the old rule that still hold, and should keep holding:

- **`services/keys.py` is the gate on anything key-addressed.** `clean_name`
  refuses a slash rather than escaping it — a rename must not be able to become a
  move — and `assert_inside_root` refuses an operation aimed at the root, so
  "delete the library" is not expressible through the API. This used to be
  described as the first of two lines of defence with IAM behind it; with the
  prefix empty it is the only one, which is the reason to be conservative when
  changing it. **What it is not is a library boundary** — it is a string check
  against one prefix, and one prefix is the whole bucket. #312 shrinks it to
  classification and naming as the key-addressed routes retire.
- **Upload exists as of #294; multipart still does not.** This bullet used to
  read "No upload, and no multipart grant", and it asked for the reversal to be
  argued separately rather than arriving as a side effect. It was.
  `POST /api/nodes/<id>/upload-url` signs a PUT and `POST
  /api/nodes/<id>/confirm-upload` finalises the row once `HeadObject` succeeds.
  The 6 MB Lambda request limit — the obstacle that made this more than a policy
  question — is answered by the bytes never transiting the Lambda at all.
  What bounds it is the signature, not the IAM policy: one key
  (`blobs/<node_id>`, never one the caller names), one exact content length, one
  content type, and a TTL shorter than a read URL's. `content-length` and
  `content-type` are signed headers, so an oversized body is refused by S3
  rather than discovered after it has moved.
  The only other `PutObject` is an overwrite of an *existing* text file
  (`manage.update_text`, capped at `max_text_bytes` and refused outright for a
  node with no blob, so it cannot create). **The zero-byte folder marker is
  gone** (#316): a folder is a row, so there is nothing left for a marker to
  fake and nothing left that reads one.
  **Still no multipart grant**, and `max_upload_bytes` is S3's single-PUT
  ceiling rather than a policy number — past it a single `PutObject` is
  impossible, which is a separate decision again.
- **`copy_objects` is the only `CopyObject` left.** It used to be one of four:
  a rename, a folder rename and a move were each a copy per key followed by a
  delete. #316 made all three catalog transactions that move no bytes at all, so
  the one copy remaining is the one that was always *supposed* to duplicate
  something. Each copy gets its own object rather than a second row pointing at
  one key — `catalog.delete_node` does not ask whether a blob is still
  referenced, so a shared key would mean deleting one copy destroyed the other's
  bytes. Copy-on-write is #334 and has to revisit that. The
  bytes come from inside the bucket — which used to make "studio cannot upload"
  true as a whole, and no longer does. `copy_objects` is still not an upload;
  the upload is `POST /api/nodes/<id>/upload-url`, above, and it is the only
  path by which bytes from outside enter the bucket.
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

### The catalog grant, and why the boundary is not in IAM at all

**Under the catalog the S3 grant cannot express the security boundary, and
neither can the DynamoDB one.** Say that plainly rather than leaving the prefix
argument above to be read as one, because the prefix argument is where a reader
arrives from and it no longer generalises:

- **A row has no prefix to scope by.** `blob_key` is deliberately opaque — prod
  holds `characters/<slug>/…` keys written years before the table beside
  `blobs/<node_id>` keys written after it — so there is no string an IAM
  condition could match that means "this library".
- **Membership is a table lookup, not an identity.** Whether a caller may see a
  node is answered by a `USER#<sub>` query, on rows the same policy grants
  access to. IAM cannot ask a question whose answer is in the data it is
  guarding.
- **Two nodes in different libraries are two items in one partition space.**
  There is no per-library partition to condition `dynamodb:LeadingKeys` on and
  there deliberately is not one: `lib` is an attribute a transfer rewrites
  (#322), and a key you can move an item across is not a key you can authorise
  on.

So the policy's job is narrow — grant the six item operations the model
performs, on this table and `<arn>/index/*`, and nothing that changes what the
table *is*. `Scan` is absent because a scan crosses library boundaries by
construction. `BatchWriteItem` is absent because a node is two items and every
write is a `TransactWriteItems`. `CreateTable`, `DeleteTable` and everything
touching PITR are absent because nothing reachable from the internet should be
able to delete the library outright.

**What holds the line instead is membership, checked in
`services/catalog.py`'s callers inside the API.** Every node response is checked
against the node's own `lib` — not against the library the request claimed —
because a node id is shareable and the node's own answer is the only
authoritative one. `before_request` resolves the caller's library once per
request from `X-Studio-Library`, a sole membership, or a refusal. That is the
boundary. It is code, it is one consistency boundary, and it is the reason the
API is the only writer to this table.

**The consequence for reviewers: an IAM diff can no longer tell you whether the
boundary moved.** It could when the answer was a prefix. Anything that widens
who can see what is now a change in `routes/nodes.py`, `routes/libraries.py` or
`app_factory`'s request hook, and reads as ordinary application code. #332 is
open on whether IAM should express any of it; until it is decided, do not read a
clean Terraform plan as evidence.

**A row has no version history either**, and this is where the two stores stop
being analogous. An overwrite during a move or a transfer rewrites `path` or
`lib` across a whole subtree and leaves nothing behind. The bucket's tombstone
guarantee below has no counterpart here — the catalog's only recovery is the
table's PITR, restored out of band by a human into a new table, plus
`deletion_protection_enabled` refusing a `DeleteTable` at the API rather than
only in Terraform.

### The bucket's own protections, unchanged

There is **no second copy of this bucket anywhere.** An older mirror called
`xharness-assets` used to exist and this file used to offer it as a fallback;
it has since been deleted, and the note is removed rather than left to be
believed. Versioning and `prevent_destroy` are what stand in its place.

`xharness-prod-media-us-east-1`, the bucket this one was renamed out of, is not
a fallback either: it was deleted in August 2026 once the copy was verified, and
its version history went with it. Nothing stands behind this bucket now.

## What the library looks like

**The tree below is the catalog's, not the bucket's.** Rows carry the names,
the parents and the shape; the bucket carries bytes under whatever key a row
happens to point at. The two agreed exactly, key for name path, up until the
catalog was seeded — which is what let the read path move onto rows without the
SPA noticing (#309) — and they have been diverging ever since. Read the diagram
as the folder tree a person sees.

**Two kinds of `blob_key` exist, and both are correct forever.** Anything
written before the catalog keeps the key it was written under
(`characters/<slug>/…`, `projects/<slug>/…`); anything written through
`POST /api/nodes/<id>/upload-url` since gets `blobs/<node_id>`, which
`catalog.blob_key_for` is the single definition of. **A legacy key is a pointer
with no meaning left in it.** It reads like a path and is not one — a rename
does not touch it, a move does not touch it, and nothing outside
`services/catalog.py` may split it on `/`. The moment something does, the
coupling the catalog was built to remove is back, and it is back only for the
half of the library that is old enough to look tempting. #335 is open on
normalising the legacy keys; until then, `blobs/` sitting alongside
`characters/` in the bucket is the expected state and not a mess to tidy.

Because a row and a blob are deleted separately, a blob can outlive every row
that pointed at it. That is what `studio catalog gc` is for (#318) — it is the
only sanctioned way to find an orphan, precisely because "unreferenced" is a
question only the table can answer.

**There is no `media/` wrapper.** There was until August 2026, and studio's
browsable root was hard-coded to it in five places — the Flask config default,
the SPA's `ROOT_PREFIX` (gone since #313, which took the paths out of the SPA's
URLs), the Terraform variable, the IAM prefix condition and the deploy
workflow's `jq` block. When the pipeline flattened the bucket, every
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
config/pose/                    # shared pose plates; source of truth is the repo
blobs/<node_id>                 # bytes uploaded through the API — no tree, by design
```

Three things about this shape drive the UI: run and scene folders sort
chronologically because their names start with a timestamp; a run's output lives
one level down in `output/`, so a run folder itself usually shows only JSON; and
a subject is split across two top-level trees — `characters/<name>/` and
`projects/<name>/` are the same subject, and reel mode is what puts them back
together, since it walks recursively from wherever you are.

There used to be a fourth, and it is retired rather than deleted because anyone
who read this file before will look for it. **"A folder has no LastModified"**
was true of a delimited listing, which returns common prefixes, and a common
prefix is not an object. So the date sorts fell back to the folder's name — which
for a run folder *is* its date — and this file warned against HEADing every
prefix to invent a timestamp. A folder is a row now (#311), stamped by
`catalog._now` like every other row, and `_folder_entry` carries
`last_modified`. The warning is gone with the constraint; the reason it was
right is that the fix it forbade would have been a per-prefix round trip to
reconstruct something the data did not have.

The pipeline owns this layout and has reshaped it before. When it changes again,
the catalog is what has to be reshaped with it — `media_root_prefix` narrows the
key-addressed remnant and the Lambda's S3 policy, and narrows nothing about what
a query returns.

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
  cross-origin `fetch` to S3 would need a CORS configuration on the media
  bucket. Studio does own that bucket now (`infra/modules/media`), so this is a
  decision rather than an impossibility — and the decision is no: one
  authenticated same-origin request beats a second CORS surface whose allowed
  origins would then have to agree with the four places the API's already do.
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
  by emptying what was being moved. Selection is keyed by node id rather
  than by grid index: a listing can be re-fetched underneath one — every write
  does exactly that — and an index-keyed selection would quietly come to mean
  different files. It held the object key until #313 and holds the id for the
  same reason one press further on: an id survives the rename that changes a key.
- **The URL names a node by id, and CloudFront still has to be in on it.**
  `/f/<node_id>` is a folder and `/o/<node_id>` is one file, open; `/` is the
  library root, whose id nothing knows before the first request. `utils/location`
  is the whole of that mapping. The URL used to *be* the S3 key, which meant
  renaming a clip invalidated every link to it — a node id is the one thing about
  a node that never changes, so a share link now outlives both a rename and a
  move.
  - **The old links still work, through one resolver.** Anything matching
    neither id route goes to `pages/LegacyRedirect`, which asks
    `GET /api/resolve` what the name path names and `replace`s itself with the id
    URL. `replace` is load-bearing: leaving the old URL in history makes back
    re-enter the resolver and push forward again. The node's `kind` picks the
    route, so a link that lost its trailing slash in a chat client still lands
    right. **This is the only tested part of the frontend** — see Testing below.
  - **Do not simplify the viewer-request function to extension matching.** A
    legacy share link *ends in `.mp4`*, so `modules/hosting` routes by
    **location** (`/assets/…` and `/index.html` pass through, everything else
    rewrites) rather than by "does this look like a file". That rule serves the
    extensionless id URLs and the legacy ones alike and needed no change for
    #313. The extension-matching version it replaced sent every share link to
    S3, where the 403/404 fallbacks rescued it into `index.html` — it worked, by
    accident, one wasted origin round trip at a time.
- **An object URL names the file, not its folder, so the folder is asked for.**
  `hooks/useFolder` reads `parent_id` off `GET /api/nodes/<id>` — but only when
  the listing already in hand does not hold the file. That is what keeps a reel
  scrolling forty clips at zero requests: it rewrites the URL to each one, and
  every one is in the listing. A cold share link asks once. Keeping the last
  folder instead would be wrong rather than merely lazy — going back into an
  object URL after browsing elsewhere would keep a folder the file is not in.
- **Names and paths come off the breadcrumbs.** The folder's own name, its
  parent and whether it is the root were string arithmetic on the URL and are
  now read from the trail `GET /api/tree` returns, which the server built by
  walking `parent_id`. Rebuilding any of it client-side would be a second,
  guessing implementation — and a path↔id translation layer in the SPA is
  exactly what #313 exists to avoid.
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
- **The reel's cursor is still an offset, and the reason changed underneath it.**
  This bullet used to say "an offset, not an S3 continuation token", and the
  contrast is retired: there is no S3 listing left to have a continuation token.
  `reel_items` enumerates *rows* — a `by-recent` query from the library root, a
  `by-path` `begins_with` from anywhere else (#310) — bounded by
  `STUDIO_MAX_FOLDER_OBJECTS`, which replaced `STUDIO_MAX_WALK_OBJECTS` and its
  twenty-thousand-object walk. **It is still fetch-then-sort**, because sorting
  by date means the whole branch must be known before a page can be cut from it
  and `name` is not an order either index offers. What improved is what is
  enumerated, not the complexity. Presigning still happens *after* the slice —
  one page's worth of URLs, never the branch's. Keep it that way.
  The enumeration bound **truncates** rather than refusing, and says so in
  `truncated`: a page of a library may be shorter than the library, and a caller
  showing one should say so rather than imply the tail does not exist.
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
  `GetObject` — on the routes that still take a key.** `/api/asset`, `/api/text`
  and the key-addressed write routes normalise and confine every prefix and key
  to `config.media_root_prefix()`. That root is empty in prod, so the
  confinement check passes everything and the traversal rules (`..`, a leading
  `/`, a backslash — all rejected before normalisation) are what is actually
  holding the line. Test changes to it directly — `posixpath.normpath` strips a
  trailing slash, which is why the folder check happens on the raw value, and it
  is why the tests set a non-empty root to keep the confinement branch covered.
  **Nothing id-addressed goes through it**, and that is not an oversight: a name
  is looked up as an exact `NAME#` sort key and `clean_name` refuses a slash, a
  `.`, a `..` and a control character on the way *in*, so `../elsewhere` is a
  name nothing is called rather than traversal to reject. `keys.kind` and
  `keys.language` — extension classification — are used by both halves and
  survive #312; the confinement half does not.
- **`.heic` is not in `IMAGE_EXTENSIONS`, and a couple of seed photos are
  `.heic`.** They list as ordinary files rather than tiles. That is the current
  behaviour, not a considered decision — but before adding the extension, note
  that Chrome cannot decode HEIC, so a tile would render as a broken image
  rather than a photo.
- **The Lambda's env vars come from the deploy workflow, not from Terraform.**
  `lifecycle { ignore_changes = [environment] }` means the `environment` block
  in `modules/compute` only applies the first time the function is created;
  after that the `jq` block in `studio-prod.yaml`'s `update-lambda` job is the
  only thing that sets `STUDIO_MEDIA_ROOT_PREFIX` and `STUDIO_CATALOG_TABLE`.
  Change one without the other and the value you read in the code is not the
  value that is running. `--environment` **replaces** the map rather than
  merging into it, so that document has to be complete: dropping a line unsets
  the variable on the next deploy. `STUDIO_MEDIA_ROOT_PREFIX` is also
  legitimately the empty string — do not "fix" it by dropping the line.
  `STUDIO_CATALOG_TABLE` is the one that changed character: it was inert while
  listings came from S3, and since #309 an unset value is the difference between
  a browsable library and an empty one.
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
- **Ties in a date sort used to be the common case. They are not any more, and
  the tie-break is gone.** S3's `LastModified` has one-second resolution and a
  run writes its whole output inside one second, so a date sort tied almost
  everywhere: `_sort_files` had to sort by full key first and by date second —
  two passes over a stable sort — or `newest` handed back `frame_9, frame_8,
  frame_7` for every run. `catalog._now` stamps microseconds, so `_sort_records`
  is one pass and equal timestamps now mean equal *instants* rather than equal
  seconds. Python's stable sort leaves those in the order the query returned
  them. Do not reintroduce a secondary key to "make it deterministic" — the
  thing it would sort on is `blob_key`, which is opaque and which a rename does
  not change.
- **A listing sorts on one date and shows that same date.** `_timestamp` returns
  `updated_at`, falling back to `created_at` only for a row old enough to predate
  the pair. A listing ordered by a date it does not display reads as a bug
  forever, which is the whole reason there is one accessor rather than two
  fields.
- Lambda uses `lifecycle { ignore_changes = [image_uri, environment] }`; the
  deploy workflow owns the image tag and the env vars.

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

**Two addressing schemes, and which one a route uses is the fastest thing to
check about it.** Everything on `/api/nodes*`, `/api/libraries` and
`/api/resolve` takes a **node id**. `/api/tree` and `/api/reel` take either. The
rest — `/api/asset`, `/api/text`, and every write under `/api/folder`,
`/api/object(s)` — takes a **key or prefix**, which is the older surface: the
SPA still calls it, and #312 and #316-onwards retire it. Nothing new should be
added to it.

| Route | Returns |
|---|---|
| `GET /api/health` | `{"status": "ok"}` — liveness, touches neither store |
| `GET /api/libraries` | `[{id, name, role}]` — the caller's libraries. Authenticated, **not** library-scoped |
| `GET /api/nodes?parent=` | The children of one folder, name-ascending. 404 unknown parent, 403 another library |
| `GET /api/nodes/<id>` | One node. 404 unknown id, 403 another library |
| `GET /api/resolve?path=` | A slash-joined name path → the node it names. An empty path is the library root |
| `POST /api/nodes` | `{parent, name, kind, blob_key?}` → creates a folder or a file. **201.** 409 if the name is taken |
| `PATCH /api/nodes/<id>` | `{name}` to rename **or** `{parent}` to move — both at once is a 400, not a guess |
| `DELETE /api/nodes/<id>` | Node and subtree. Rows first, then blobs |
| `GET /api/nodes/<id>/download-url` | A fresh presigned GET for the node's blob. `disposition=attachment` to download |
| `POST /api/nodes/<id>/upload-url` | `{size, content_type}` → a presigned PUT for `blobs/<id>`. Signed length and type |
| `POST /api/nodes/<id>/confirm-upload` | `HeadObject`s the blob and writes `size`/`content_type` onto the row |
| `POST /api/runs` | Records a run: folder, documents inline, and an upload URL per output |
| `GET /api/tree?node=\|prefix=&sort=` | One folder ready to draw: `folders`, `files` (each presigned), `breadcrumbs`, `counts`. One address or the other — both is a 400 |
| `GET /api/reel?node=\|prefix=&cursor=&page_size=&sort=` | Images and video beneath a folder, recursively, paginated. Same two addresses |
| `GET /api/asset?key=&disposition=` | A fresh presigned URL for one object |
| `GET /api/text?key=` | A `.json` / `.md` / `.txt` object's contents, capped at 1 MB |
| `POST /api/folder` | `{prefix, name}` → creates an empty folder. One row, no object. 409 if taken |
| `PATCH /api/object` | `{key, name}` → renames one file in place. 409 if taken |
| `PATCH /api/folder` | `{prefix, name}` → renames a folder. Its subtree does not move |
| `POST /api/objects/move` | `{keys: [...], destination}` → moves 1..N files, names kept. 409 if taken |
| `POST /api/folder/move` | `{prefix, destination}` → moves a folder; descendants' `path` is rewritten |
| `POST /api/objects/copy` | `{keys: [...], destination}` → copies 1..N files, sources kept. Names numbered if taken |
| `PATCH /api/text` | `{key, content}` → overwrites a text file's bytes and restamps its row |
| `DELETE /api/objects` | `{keys: [...]}` → deletes 1..N files. Rows first, then blobs |
| `DELETE /api/folder` | `{prefix}` → deletes a folder and its subtree. Rows first, then blobs |

**The eight routes above take a name path, not an S3 key** (#316, #317, #319).
`prefix`, `key` and `destination` are the slash-joined names `GET /api/tree`
hands back and every share link is made of; `services.manage` walks them against
the catalog one `NAME#` lookup per segment, starting at the library's root.
Nothing changed on the wire, which is why the SPA needed no change. For material
written before the catalog a name path and a blob key are the same string; for
anything written since they are not, and nothing may assume they are.

**That also retired the confinement they used to need.** `keys.clean_prefix` and
`assert_inside_root` normalised a string and compared it against
`media_root_prefix`, which in prod is empty and therefore excluded nothing. A
walk cannot leave the library it starts in, so `../elsewhere` is not traversal to
reject — it is a name nothing is called, and it 404s. Those functions and five
more now have no caller; #312 removes them.

**Rename and move are separate routes and must stay separate.** A rename takes a
`name` and changes the last segment; a move takes a `destination` folder and
changes the parent. `keys.clean_name` refuses a slash, so a rename cannot become
a move by punctuation, and a destination is always read as a folder, so a move
cannot become a rename by typing a filename into it — under S3 `move(x.jpeg →
a/b.jpeg)` put the file *inside* a conjured `a/b.jpeg/`, and against the catalog
the same request is a 404 because no folder is called that. The asymmetry is
deliberate, the refusal got louder, and the tests pin both.

**A conflict is a transaction condition failure, not a listing.** Every create,
rename and move puts its `NAME#` item under `attribute_not_exists(pk)` and turns
the cancelled transaction into the 409 the API always returned. The check used to
be a read followed by a write with a window between them; the window is gone
rather than narrowed. A bulk move still pre-checks every destination with a read,
because each file is its own transaction and a conflict found on the eighth would
leave seven already moved — that read is a courtesy, and the condition expression
is the guarantee.

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
name-path side rename and move are different routes, and `keys.clean_name`
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
| `STUDIO_MAX_FOLDER_OBJECTS` | 2000 | A subtree operation the Lambda can finish — **and the reel's enumeration** |
| `STUDIO_MAX_TEXT_BYTES` | 1 MiB | What `/api/text` will read and `PATCH /api/text` will write |
| `STUDIO_MAX_UPLOAD_BYTES` | 5 GiB | S3's single-PUT ceiling, declared at signing time |
| `STUDIO_PRESIGN_TTL_SECONDS` | 900 | A read URL's requested life |
| `STUDIO_UPLOAD_TTL_SECONDS` | 300 | An upload URL's — deliberately shorter |

**`STUDIO_MAX_WALK_OBJECTS` (20,000) is gone.** It bounded a walk over S3
*objects*; the reel enumerates rows now (#310), so `STUDIO_MAX_FOLDER_OBJECTS`
bounds both and there is one number for how much of a subtree this service holds
in memory rather than two that had drifted an order of magnitude apart. Nothing
in Terraform or the deploy workflow ever set it, so there is no infra drift
behind it — but if you find it pinned in a shell or an `.env`, delete the line:
it configures nothing.

The same number means two different things, deliberately. For a **subtree
operation** it is a **refusal** — a rename that stopped halfway would leave the
same objects under two prefixes with no record of which half moved. For the
**reel** it **truncates**, and says so in `truncated`, because a page of a
library is allowed to be shorter than the library. Renames copy before they
delete, in that order and never the reverse — a failed delete leaves a
duplicate, which is visible and fixable, while the reverse order would lose
data.

## Local development

**A per-machine dev stack comes first, and `dev-up.sh` refuses to start without
one.** Studio ran local-against-prod until August 2026; it does not any more.
The stack is this machine's own Cognito pool, media bucket and catalog table,
named `studio-dev-<short12>-*` from a persistent UUID in
`~/.config/andreas-services/studio/machine-id`. Failing early is deliberate: an
API with no pool 500s on every call, which is a slower way to learn the same
thing.

```bash
aws login
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
eval "$(aws configure export-credentials --format env)"   # boto3 needs real env creds
poetry run python -m studio_core.handlers.local.api.api_dev_server
poetry run pytest                                          # moto-backed, no AWS needed

cd studio/frontend
export NODE_AUTH_TOKEN=$(gh auth token)                    # needs read:packages
npm ci && npm run dev
npm test                                                   # vitest, no AWS needed
```

`aws login` writes a cache only the AWS CLI reads, so `aws sts
get-caller-identity` succeeding tells you nothing about whether boto3 can see
credentials — export them. Same split the root `CLAUDE.md` documents for
Terraform's provider.

`dev-setup.sh` writes `frontend/.env.local` **from this machine's dev stack's
Terraform outputs** and installs `frontend/node_modules` — do not hand-copy the
example or hand-edit the result; the generated file says as much in its own
header. It used to read `/studio/prod/*` from SSM and pin the live pool and the
live bucket, and that sentence stood in this file until #287; SSM holds what the
deploy workflow wrote, and nothing deploys a dev stack. Without the env file the
app shows "Auth is not configured"; without node_modules every local binary is
missing, and the first one you hit is `tsc: not found`.

The script runs from the SessionStart hook and **tolerates a missing stack**,
warning and carrying on — it still has a toolchain to install. It also warns
loudly, rather than rewriting, about a `studio/.env` that pins a prod bucket or
a dead `XHARNESS_S3_*` name. The file is the developer's; silently repointing
where their commands write is worse than telling them.

## Testing

**The backend has a suite; the frontend has one test, and that asymmetry is
deliberate.** `backend/tests/` is moto-backed pytest over a miniature of the
catalog table and the bucket, and covers the whole read and write surface. It is
moto and not a real stack on purpose: the dev stack costs an apply, and a suite
that needs AWS is a suite that stops being run. `frontend` ran on
`lint → typecheck → build` alone until #313, on the reasoning that every failure
this SPA can have is a blank page somebody sees immediately.

The legacy-URL resolver broke that reasoning, so it got a runner. A share link
written before #313 that quietly stops resolving is invisible until a user
reports it — there is no blank page, because the app is working perfectly for
everyone who never had one. `vitest` + `@testing-library/react` + `jsdom`,
`npm test`, run in `studio-pr.yml` beside lint and typecheck.

`src/pages/LegacyRedirect.test.tsx` and `src/utils/location.test.ts` are the
whole of it, and what they assert is: an old `/projects/…` URL resolves **once**
and lands on the id URL with its `?sort=` intact; `replace` keeps the old URL out
of history, so back does not walk into the resolver again; the node's `kind`
picks `/f/` or `/o/`; a 404 is shown rather than swallowed into a redirect to the
root; an id URL reaches `BrowsePage` with no resolve at all.

Two things follow for anyone adding to this. The route table lives in
`routes.tsx` rather than `App.tsx` so it can be exercised without the auth stack
— the gate renders a "not configured" notice when no user pool is set, which in a
test is every URL resolving to the same thing. And `vite.config.ts` sets both
`clearMocks` and `restoreMocks`: "the resolver was not called" is one of the
assertions and is worthless against a tally shared with the previous case.

**Everything else on this surface is typecheck-only.** That is the honest state,
not an oversight, and the bar for the next test is the resolver's: a failure the
app cannot report on its own.

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
