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
for each is in **What this service may do to the library** below — read it
before widening it a third time.

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

**And the SPA can now drive that upload**, which #294 built the routes for and
left unreached. There is an Upload button on the folder toolbar; it takes any
number of files, puts them into the folder on screen, and does nothing
character-aware or project-aware — a folder is a folder. **An uploaded file keeps
the name it arrived with**, and a name the folder already holds is *numbered*
(`clip.mp4` → `clip (2).mp4`) rather than refused or overwritten, which is the
form `POST /api/nodes/copy` has produced since #317. The `<project>_in_<n>` and
`<name>_<group>_<n>` conventions are **not** applied here and nothing on this
side depended on them — `refs.py`: "Slot N is position N in the resolved
selection, not a trailing file number". They are **not retired**: the pipeline
still numbers its own input pool `<project>_in_<n>.<ext>` on every
`projects.add_inputs`, reading the highest N off the names rather than counting
them. It is simply not the app's business what a folder's names mean.

Where the numbering happens is a decision worth stating: **in the API**
(`catalog.create_numbered`), not in the browser. A client-side version would be a
second implementation of a convention that has to agree with copy's, disagreeing
only in a folder that had been through both; and it would have to pick a name
from a listing that is already stale by the next file, where the conditional put
on the `NAME#` item is the only authority on whether a name is free.

## Stack

| Layer | Choice |
|---|---|
| Backend | Flask (Python 3.11) + Mangum, Docker container Lambda behind API Gateway REST |
| Frontend | Vite + React 19 + Tailwind v4 + the design system's **web** leaves, static build to S3 + CloudFront |
| Auth | AWS Cognito (admin-create-only user pool); **Cognito Managed Login** (hosted pages at `studio-auth.andreas.services`) with the authorization-code flow + PKCE on the SPA, Cognito authorizer on every `/api` route. The `studio` CLI still signs in with SRP directly — see `infra/modules/auth`. |
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
│   │                         #   media, catalog, dev_storage, dev_seed
│   ├── envs/prod/            # applied by CI
│   └── envs/dev/             # per machine, applied only by scripts/dev-aws-*.sh
├── pipeline/                 # the generation half's code — local only, never deploys
├── scripts/                  # create-user.sh, add-member.sh; dev-setup.sh / dev-up.sh;
│                             #   dev-aws-{setup,reset,destroy,seed}.sh, dev-shared-material.sh,
│                             #   dev-user.sh, dev-token.sh;
│                             #   prod-seed-smoke.py, prod-github-set-secrets.sh
├── .claude/skills/           # the generation half's docs — local only, never deploys
├── docs/
│   ├── PIPELINE.md           # the local half
│   ├── PROD_SMOKE.md         # the post-deploy smoke run
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
pipeline runs from a laptop, and since #308 it holds **no AWS credentials at
all** — it signs in with `studio login` and comes through this same API. This
sentence said "under a human's own AWS login" and predates that. This Lambda is
still the only thing reachable from the internet, so it is still the thing worth
scoping, and everything below still applies to it.

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

- **`services/keys.py` is classification and naming, and one raw key** (#312).
  `clean_name` refuses a slash rather than escaping it — a rename must not be
  able to become a move — and that refusal is about *names*, not about S3, so it
  is untouched. What went was the confinement half: `clean_prefix`,
  `assert_inside_root` and the five prefix-arithmetic helpers had no caller left
  once every route took a node id or a name path. "Delete the library" is not
  expressible because the root node has no `parent_id` and so no `NAME#` item to
  rewrite — the same refusal, arrived at from the data instead of from a string
  comparison. `clean_key` stayed for one parameter and has since gone with it —
  shared material has nodes now, so nothing is addressed by key.
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
  **A failure between the row and the bytes leaves a placeholder, and #442 made
  it invisible again.** The node is minted first, because its id is what names
  the key, so anything that goes wrong after that leaves a row naming
  `blobs/<id>` with nothing behind it. `browse._file_entry` presigns *any* row
  carrying a `blob_key`, so the grid used to draw that row as a tile that would
  not load. `browse.is_abandoned_upload` now keeps it out of the listing and out
  of the reel, keyed on `size` being **absent** — `"size" in record`, not
  truthiness, because a confirmed empty file has `size` 0 and a placeholder has
  no `size` at all.
  **`studio catalog gc` (#318) does not collect it.** That command deletes blobs
  no row names; a placeholder is a row no blob answers, the opposite direction,
  and nothing collects it. So the SPA's uploader deletes the node itself when a
  PUT fails, and the hidden row is what is left when that cleanup fails too.
  **A failure at the *confirm* is NOT the harmless case this paragraph used to
  call it.** It said the bytes are there and the row names them, so "only `size`
  reads 0" — wrong twice, and expensively. `size` is absent rather than 0, and
  the consequence is not a cosmetic number: the row is hidden from every listing
  and from the reel. That reasoning is what made it look safe for
  `store.upload_to_url` to PUT an entity's output and skip the confirm, which
  left all 170 run outputs in prod in exactly this state — in S3, named by their
  run, drawn on the run page, and absent from the `output/` folder they lived in.
  It confirms now, and `studio catalog confirm-outputs` repairs what shipped
  before it did.
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
  erase history. Every delete of an *object* it can perform is recoverable. With
  the prefix confining nothing, this is the strongest guarantee left standing —
  do not drop it to tidy the policy.
  **It says nothing about a row**, and the two are now deleted separately:
  `DELETE /api/nodes/<id>` removes rows first and blobs second, so a delete that
  half-succeeds leaves recoverable bytes nothing can name. Read this guarantee
  as exactly what it is — the bytes survive — and read the next section for what
  covers the half that does not.

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

**A `blob_key` is `<characters|projects|libraries>/<entity id>/<node id>.<ext>`**,
stamped once when the node is created from the owner its parent already resolves
to, and `catalog.blob_key_for` is the single definition. It carries an id and
never a name, so a bucket listing no longer spells out every character in the
library — which is hard rule #1 applied to the one place that had been quietly
breaking it. Unaffected by the rule going env-scoped: the exception is for a
**dev subject** in the repo, and this is the production media bucket.

**It is still a pointer with no meaning in it.** A rename does not touch it, a
move does not touch it, and nothing outside `services/catalog.py` may split it
on `/`. The prefix is an operational convenience — per-entity cost in Storage
Lens, a lifecycle rule, a bulk delete that is one prefix — not an address. Move
a file between entities and the prefix goes stale while the key stays correct;
`studio catalog verify` reports that drift and `reseat` fixes it, out of band and
never automatically.

Four older shapes survive in prod and all of them are correct forever:
`characters/<slug>/…` and `projects/<slug>/…` from before the catalog,
`blobs/<node_id>` from between the catalog and the entity model, and
`<entity>/<id>/<folders>/<filename>` — 182 keys — from the spell when the key
was descriptive and `reseat` rewrote the library into it. Nothing parses any of
them, which is exactly why they can be left alone; a reseat clears the fourth
because a flat key is what `desired_key` builds again, and leaves the other
three, which no `desired_key` has ever claimed.

**`is_api_blob` has to keep accepting the descriptive shape**, and narrowing it
to the flat one after a reseat would be a regression rather than a tidy-up: it
gates whether a signed upload may overwrite an object, and a signature makes a
refusal permanent the moment the URL is handed out. That exact narrowing already
took the whole production library out of write once.

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
<subject>/                      # a character's folder; its record names it `root`
├── seed/                       # source photos (.webp, .jpg, .jpeg, .JPG, .heic)
├── corpus/                     # the wider photo set
├── reference/                  # the images its REF# rows point at,
│   └── <face|body|frame|wardrobe>/   #   grouped by purpose
└── archive/                    # superseded output kept around
<project>/                      # a project's folder
├── runs/<run id>/              # request.json, result.json, sometimes prompt.json
│   └── output/                 # the generated .jpeg / .webp / .mp4
├── scenes/<slug>/              # storyboard/ + shots/ + output/
├── chains/<name>.json          # a scene's shot-to-shot plan
└── input/                      # the working pool
config/pose/                    # the pose plates; source of truth is the repo
```

**No `characters/` or `projects/` wrapper**, and no `profile.yaml`,
`project.json`, `scene.json` or `movie.json`. Each of those was a document that
had to be read to answer a question the catalog can now be asked, and each is a
row. An entity's folder is a top-level node its record names, so the two are
found in opposite directions: the record names `root`, and the root node carries
`entity` back.

The bible, the project's description, a scene's shot list and a run's envelope
are all rows. What stays a file is what studio does not own: a run's
`request.json` and `result.json` are the provider's bytes, served as text and
never parsed — the rule below, now true of a much smaller set of things.

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

- **A run page shows three different kinds of thing, and conflating them is the
  one mistake to avoid here.** The *envelope* is studio's and safe to render as
  fields. The *payload documents* are the provider's and are shown as text and
  never decoded — that rule survived the entity model by moving to where it is
  actually true. The *plan* is studio's too, and is the authored half a run
  gained: the prompt, the params, and one ordered `SEND#` row per bound image
  with its role and provenance. `bindings` is derived from those sends and only
  falls back to the stored attribute for a run the backfill has not reached.
  See [RUN_PLAN.md](RUN_PLAN.md).
- **Approving in the app is a real write, and it is bound to a hash.** `POST
  /api/runs/<id>/approve` sends the digest the page was showing; the API
  recomputes and answers 409 if the payload moved. It is not a permission
  boundary — the CLI holds the same kind of token — so the page states the
  digest in words rather than implying an authority it does not have.
- **The API takes the ID token, never the access token.** A REST
  `COGNITO_USER_POOLS` authorizer only reads the incoming token as an *access*
  token when the method declares `authorization_scopes`. This one declares none
  — and cannot usefully, since the pool has no resource server and the code
  flow's `openid email profile` are identity scopes rather than custom ones —
  so it validates an *identity* token. Send the stored `idToken`
  (`auth/oauth.ts`, read by `apis/client.ts`); the code flow still issues one
  because `openid` is requested. The failure mode is the confusing one: sign-in
  succeeds, the app renders, and every `/api` call 401s.
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
- **Text is served through `/api/text`, not fetched from the presigned URL.** A
  cross-origin `fetch` to S3 would need a CORS configuration on the media
  bucket. Studio does own that bucket now (`infra/modules/media`), so this is a
  decision rather than an impossibility — and the decision is still no: one
  authenticated same-origin request beats widening a rule whose allowed origins
  would then have to agree with the four places the API's already do.
  **The bucket does have a CORS rule now**, which this bullet used to say it did
  not, and the rule is one line: `PUT`, `content-type` + `content-length`, no
  exposed headers. It exists because the *upload* is a cross-origin PUT the
  browser preflights, and without it every upload fails with no status attached.
  `GET` is deliberately not in it — adding one would make this bullet's trade a
  live question again. Reads need nothing either way: the app draws media with
  `<img src>` and `<video src>`, and plain media loading is not subject to CORS.
- **The upload PUT is `XMLHttpRequest`, and it is the only request in the SPA
  that is not `fetch`.** `fetch` cannot report upload progress — its `Response`
  is the *download*, and streaming a request body to count it yourself needs
  `duplex: "half"` over HTTP/2, which Safari does not do. A 300 MB clip going out
  over a phone connection behind an indeterminate bar is indistinguishable from a
  frozen tab, so `upload.onprogress` is the feature rather than a nicety. See
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
  Safari — an upload that appears to succeed and produces a file the library
  cannot show. The refusal happens before the node is created and names the fix
  (Settings › Camera › Formats › Most Compatible).
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
    right. **This was the first tested part of the frontend, and is no longer
    the only one** — see Testing below.
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
  `truncated`: a page of a library may be shorter than the library. The SPA
  carries it through `useReel` to `ReelView`, which renders the count as
  `12 of 2000+` — the `+` is the whole of the UI for it, and it is enough,
  because the alternative is a reel that silently claims the library ends where
  the cap did.
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
  where the API refuses it anyway — the root node has no `parent_id`, so there
  is no `NAME#` item to delete. Leaving is the one
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
- **There is no query string left that becomes an S3 key.** `GET /api/asset`
  takes `?node=` and nothing else. It was the last one, and it survived because
  that route was also how the **pipeline** read *shared* material: the
  phrasebook and the `config/pose/` plates belonged to no character and no
  project, nothing recorded a node for them, and `GET /api/resolve` 404s on a
  thing with no node.

  Both halves closed rather than one. The phrasebook is `TERM#` rows, so there
  is no document to address; the plates are ordinary nodes in a `config/` folder
  the library is created with. So `keys.clean_key`, `_normalise` and
  `_reject_traversal` are deleted along with `clean_prefix` and
  `assert_inside_root` before them, and `keys.py` is `clean_name` and the
  extension tables. One addressing scheme, no exceptions — which is what the
  confinement machinery was standing in for.

  **Nothing id-addressed or name-addressed goes through it**, and that is not an
  oversight: a name is looked up as an exact `NAME#` sort key and `clean_name`
  refuses a slash, a `.`, a `..` and a control character on the way *in*, so
  `../elsewhere` is a name nothing is called rather than traversal to reject.
  `keys.kind` and `keys.language` — extension classification — are used
  everywhere and were never in question.
- **`.heic` is not in `IMAGE_EXTENSIONS`, and a couple of seed photos are
  `.heic`.** They list as ordinary files rather than tiles. That was the current
  behaviour rather than a considered decision, and the upload made it one: an
  iPhone photographs to HEIC by default, so the uploader now **refuses** a
  `.heic` outright rather than storing a file the library cannot show. Before
  adding the extension instead, note that Chrome cannot decode HEIC, so a tile
  would render as a broken image rather than a photo — and that the seed photos
  above would start rendering as broken tiles the same day.
- **The Lambda's env vars come from the deploy workflow, not from Terraform.**
  `lifecycle { ignore_changes = [environment] }` means the `environment` block
  in `modules/compute` only applies the first time the function is created;
  after that the `jq` block in `studio-prod.yaml`'s `update-lambda` job is the
  only thing that sets the function's environment — **all six of it**:
  `STUDIO_MEDIA_BUCKET`, `STUDIO_MEDIA_ROOT_PREFIX`, `STUDIO_ALLOWED_ORIGIN`,
  `STUDIO_CATALOG_TABLE`, `STUDIO_COGNITO_USER_POOL_ID`,
  `STUDIO_COGNITO_CLIENT_ID`. This bullet named two of the six, which is exactly
  the mistake the next sentence warns about. `--environment` **replaces** the map
  rather than merging into it, so that document has to be complete: dropping a
  line unsets the variable on the next deploy, and a variable added to
  `modules/compute` and not here reads as its default in the running function
  behind a clean plan. `STUDIO_MEDIA_ROOT_PREFIX` is also
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
check about it — and there is only one left.** Every route takes a **node id**,
or an entity id where the resource is an entity. `GET /api/resolve?path=` is the
single translation from the slash-joined name path a person types into the id
everything else wants, and `slug:<slug>` addressing on an entity route is the
same courtesy for a name a person types.

The name-path *writes* are gone with `routes/manage.py`, and so is the raw-key
read: `?prefix=`, `?key=`, `/api/folder`, `/api/object(s)` and `/api/text?key=`
were all deleted. A name path is a rendering of the tree for a person to read;
nothing accepts one back.

| Route | Returns |
|---|---|
| `GET /api/health` | `{"status": "ok"}` — liveness, touches neither store |
| `GET /api/libraries` | `[{id, name, role}]` — the caller's libraries. Authenticated, **not** library-scoped |
| `GET /api/nodes?parent=` | The children of one folder, name-ascending. 404 unknown parent, 403 another library |
| `GET /api/nodes/<id>` | One node. 404 unknown id, 403 another library |
| `GET /api/resolve?path=` | A slash-joined name path → the node it names. An empty path is the library root |
| `POST /api/nodes` | `{parent, name, kind, blob_key?, on_conflict?}` → creates a folder or a file. **201.** 409 if the name is taken, unless `on_conflict: "number"` |
| `PATCH /api/nodes/<id>` | `{name}` to rename **or** `{parent}` to move — both at once is a 400, not a guess |
| `POST /api/nodes/<id>/transfer` | `{lib}` → hands the node and its subtree to another library. **Owner in both**, or 403; the node keeps its id, so every share link survives and now resolves only for the destination's members |
| `DELETE /api/nodes/<id>` | Node and subtree. Rows first, then blobs |
| `GET /api/nodes/<id>/download-url` | A fresh presigned GET for the node's blob. `disposition=attachment` to download |
| `POST /api/nodes/<id>/upload-url` | `{size, content_type}` → a presigned PUT for `blobs/<id>`. Signed length and type |
| `POST /api/nodes/<id>/confirm-upload` | `HeadObject`s the blob and writes `size`/`content_type` onto the row |
| `POST /api/runs` | Records a run: folder, documents inline, and an upload URL per output |
| `GET /api/nodes/<id>/owner` | Which entity a node belongs to, derived from its ancestry — `{kind, id, slug}` or null |
| `POST /api/nodes/move` | `{ids: [...], destination}` → moves 1..N nodes, names kept. 409 if taken |
| `POST /api/nodes/copy` | `{ids: [...], destination}` → copies 1..N nodes, sources kept. Names numbered if taken |
| `DELETE /api/nodes` | `{ids: [...]}` → deletes 1..N nodes and their subtrees. Rows first, then blobs |
| `GET /api/nodes/<id>/text` | A `.json` / `.md` / `.txt` node's contents, capped at 1 MB |
| `PATCH /api/nodes/<id>/text` | `{content}` → overwrites a text node's bytes and restamps its row |
| `GET /api/tree?node=&sort=` | One folder ready to draw: `folders`, `files` (each presigned), `breadcrumbs`, `counts` |
| `GET /api/reel?node=&cursor=&page_size=&sort=` | Images and video beneath a folder, recursively, paginated |
| `GET /api/asset?node=&disposition=` | A fresh presigned URL for one node's bytes — what the SPA calls on an expired tile |

### The entity routes

| Route | Returns |
|---|---|
| `GET \| POST /api/characters` | List, or create — record, slug claim, root folder and the starting pools in one transaction. **409** on a taken slug |
| `GET \| PATCH \| DELETE /api/characters/<id>` | One character. `<id>` may be `slug:<slug>`. `PATCH` carries `rev` and **409**s if it has moved |
| `PATCH /api/characters/<id>/profile` | `{profile, rev}` — the bible, validated |
| `GET \| POST \| PATCH /api/characters/<id>/references` | The `REF#` rows: read grouped and ordered, attach one, or describe/reorder many in one transaction |
| `PATCH \| DELETE /api/characters/<id>/references/<node>` | Change one entry's group, description, tags or order; or detach it, leaving the file |
| `PATCH /api/characters/<id>/default-set` | `{nodes: [...]}` |
| `GET /api/characters/<id>/selection` | `?pick=&tag=&limit=` → the ordered nodes a model would be shown. **Refuses** an over-cap selection with the index in the body |
| `GET /api/characters/<id>/textblock` · `/runs` · `/projects` | The identity paragraph; the runs that used it; the projects that involve it |
| `GET \| POST /api/projects` | List, or create |
| `GET \| PATCH \| DELETE /api/projects/<id>` | One project, `rev`-guarded like a character |
| `PATCH /api/projects/<id>/characters` | `{characters: [...]}` → replaces the involvement links |
| `GET /api/projects/<id>/inputs` · `/runs` · `/scenes` · `/movies` | The working pool, and the three tiers |
| `GET \| POST /api/runs` | Query by project, character, model, status, date; or record one. **Refuses a URL-shaped binding** |
| `GET \| PATCH \| DELETE /api/runs/<id>` | The envelope, with outputs and bindings expanded |
| `POST /api/runs/<id>/outputs` · `/response` | An upload URL per output; the provider's response stored as a payload blob |
| `GET \| POST /api/scenes` · `GET \| PATCH \| DELETE /api/scenes/<id>` | The scene record |
| `PATCH /api/scenes/<id>/shots` · `/shots/<shot_id>` | The plan: revise it, or change one shot |
| `POST /api/scenes/<id>/output` · `POST /api/movies/<id>/output` | Upload URL for the stitched file. **ffmpeg is not here** — the CLI stitches and uploads |
| `GET \| POST /api/movies` · `GET \| PATCH \| DELETE /api/movies/<id>` · `PATCH /api/movies/<id>/scenes` | The tier above |
| `GET \| POST /api/phrasebook` · `DELETE /api/phrasebook/<model>/<avoid>` | The wording lists, as `TERM#` rows |

**Everything above is `PATCH` where a REST habit would reach for `PUT`**, including
the whole-document writes (`/profile`, `/references`, `/default-set`, `/shots`).
`PUT` is not in the CORS method list, that list lives in four files that have to
agree, and `PATCH` is already in all four — the same trade `PATCH /api/text` made
before it. Adding `PUT` properly is a four-file change nobody has needed yet.

**`GET /api/text` was an exception twice, and is a node route now.** The
save resolved a name path to a node and wrote that node's `blob_key`; the read
did a `GetObject` on the string it was handed. So on anything uploaded through
the app — a row minted by #294, bytes at `blobs/<node-id>` — the editor could
save a file it could not then re-open. Both walk the catalog now, and both take
`?node=` as well.

**That also retired the confinement the writes used to need.** `keys.clean_prefix`
and `assert_inside_root` normalised a string and compared it against
`media_root_prefix`, which in prod is empty and therefore excluded nothing. A
walk cannot leave the library it starts in, so `../elsewhere` is not traversal to
reject — it is a name nothing is called, and it 404s. Those functions and five
more are gone (#312).

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

**`POST /api/nodes/copy` is `move` minus the delete, plus numbering.** Same
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

A folder copies as one of the `ids` like anything else, but a *deep* copy is not on offer: a subtree copy can be arbitrarily large with
no progress to report, and nothing has wanted one yet. Argue for it separately.

**`PATCH /api/text` is a PATCH because PUT is not in the CORS method list.** The
verb list lives in four places that have to agree (see below), PATCH is already
in all four, and the semantic difference is worth less than the agreement. Add
PUT properly if a route ever genuinely needs it.

`sort` is one of `newest` (default), `oldest`, `name`, `name_desc`.

The write routes carry a JSON body, `DELETE /api/nodes` included. That is
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

`aws sts get-caller-identity` is a trustworthy probe here: the CLI, boto3 and
the Terraform provider all read the same access key. Under the `aws login`
sessions this replaced it was not — the CLI read a cache the other two could not
see, and an `aws configure export-credentials` export was the workaround. The
root `CLAUDE.md` keeps that history.

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

**The backend has a suite; the frontend has thirteen test files, and how it got
from none to thirteen is the useful part.** `backend/tests/` is moto-backed pytest over a miniature of the
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

Those two were the whole of it, and what they assert is: an old `/projects/…`
URL resolves **once** and lands on the id URL with its `?sort=` intact; `replace`
keeps the old URL out of history, so back does not walk into the resolver again;
the node's `kind` picks `/f/` or `/o/`; a 404 is shown rather than swallowed into
a redirect to the root; an id URL reaches `BrowsePage` with no resolve at all.

Five more have since cleared the same bar — a failure the app cannot report on
its own:

**`pages/LegacyRedirect.test.tsx` is gone**, with the page it covered: the entity
model retired the legacy `/projects/…` resolver, so the file that started this
suite is the one file in it that no longer exists. This table listed it for
months after.

| File | What it pins |
|---|---|
| `routes.test.tsx` | which screen a URL reaches — the successor to the resolver test above |
| `utils/location.test.ts` | the id↔URL mapping: the root is `/` and needs no id, a legacy path decodes per segment so a `#` or a space in a real filename survives, and a hand-edited URL lands on the root rather than throwing |
| `apis/client.test.ts` | `X-Studio-Library` is sent once a library is chosen, absent before one is, and follows the **last** choice rather than the first |
| `apis/studio.test.ts` | `getAsset` and `getText` ask by **node**, never by key, and sign inline unless a download asked otherwise; `saveText` sends the name path `PATCH /api/text` takes |
| `components/NodeAddressing.test.tsx` | the *argument* rather than the parameter: a row carries both `id` and `key`, both are `string`, and passing `key` typechecks and then fails only on material uploaded through the app (#432) |
| `apis/upload.test.ts` | create → sign → PUT → confirm; the size declared is the file's; `Content-Length` is deliberately not set; a failed PUT does not confirm and deletes the placeholder it made |
| `components/common/LibrarySwitcher.test.tsx` | one membership shows no switcher and still sets the header; two show a switcher that reopens on the last choice and ignores a stored library the caller has left |
| `components/common/ErrorBoundary.test.tsx` | a thrown render shows a boundary rather than a white page (#495) |
| `components/common/ConfirmDeleteButton.test.tsx` | a destructive action needs a second, deliberate click |
| `components/character/ReferencesGrid.test.tsx` | the reference index draws in `(group, order)` order |
| `components/viewer/DescribePanel.test.tsx` | a description is written against the NODE, not the reference row |
| `pages/CharacterPage.test.tsx` | the selection surface: what a model would actually be shown |
| `pages/ScenePage.test.tsx` | panel state — the screen rewritten across #491, #493, #494 and #495, and the only board/panel UI coverage there is |

**Coverage is measured and gates on nothing: 36% of statements** (`npm run
test:coverage`, 2026-08-27). That is low and it is meant to be — the bar this
suite sets itself is addressing, and the rest is typecheck and the build.
`vite.config.ts` makes the argument at length. The number is there to show a
direction of travel, not to be met.

Two things follow for anyone adding to this. The route table lives in
`routes.tsx` rather than `App.tsx` so it can be exercised without the auth stack
— the gate renders a "not configured" notice when no user pool is set, which in a
test is every URL resolving to the same thing. And `vite.config.ts` sets both
`clearMocks` and `restoreMocks`: "the resolver was not called" is one of the
assertions and is worthless against a tally shared with the previous case.

**Everything else on this surface is still typecheck-only**, and the bar for the
next test is unchanged: a failure the app cannot report on its own. What the
seven have in common is that none of them is a blank page — a wrong header, a
wrong argument that typechecks, a confirm that fires after a failed PUT.

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
makes. `dynamodb:BatchGetItem` missing from the API role shipped through that
gap behind a fully green suite.

The smoke suite runs in `studio-prod.yaml` **after** the deploy, so it is a
detector and not a gate — studio has no staging. Its account is a member of
exactly one library and can reach nothing else; see
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
is how it gets diagnosed. **`scripts/add-member.sh` writes that row** (#435,
closing #321). This section used to say there was no script and that the row was
hand-written, which was an instruction to hand-edit the production catalog:

```bash
STUDIO_EMAIL=you@example.com STUDIO_LIBRARY=lib-… ./studio/scripts/add-member.sh
STUDIO_LIBRARY=lib-… ./studio/scripts/add-member.sh --list
```

It reads the `sub` off the pool account rather than inventing one, is safe to run
repeatedly, and leaves an existing membership exactly as it is — **including its
role**, because "add" quietly demoting an owner is the kind of surprise that
costs somebody their library. `STUDIO_ROLE` is `member` by default; `owner` is
the wider grant and what a transfer needs in both libraries.

Its defaults come from SSM, so they point at **prod**, like `create-user.sh` and
unlike everything named `dev-*`. Set `USER_POOL_ID` and `CATALOG_TABLE` from
`dev-aws-setup.sh`'s outputs to reach this machine's stack; there is no flag for
it, for the reason `../CLAUDE.md` gives about not designing one unprompted.

**Deliberately a script and not a route**: a route that granted membership would
be a route that could grant itself access to somebody else's library.

## Deployment

`.github/workflows/studio-prod.yaml` — `detect-changes → bootstrap-ecr →
build-and-push → deploy-infra → update-lambda + deploy-frontend`, with `smoke`
after `update-lambda` — a post-deploy detector, not a gate ([`PROD_SMOKE.md`](PROD_SMOKE.md)).
The SPA is
built in `deploy-frontend` rather than earlier because Vite inlines every
`VITE_*` value at build time and the Cognito ids come out of the apply.

Terraform state: `s3://andreas-services-terraform-state/studio/prod/terraform.tfstate`.
