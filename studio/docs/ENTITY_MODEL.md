# studio — the entity model

> **STATUS: BUILT. This is the reference.** It was a proposal, and its own
> header said so until the last of it shipped; that line is replaced rather than
> kept, because a spec that says "nothing here is built" over a model the whole
> service now runs on is worse than no status at all.

Read [What was wrong](#what-was-wrong-and-what-this-replaced) for the shape
this replaced, then go to [The data model](#the-data-model). The five decisions
it turned on are settled and recorded in
[Decisions](#decisions--all-five-settled-all-five-built); nothing below is
conditional on anything any more.

---

## What was wrong, and what this replaced

The catalog modelled **files**. Studio's users are not files — they are
**characters** and **projects**, and both were expressed as a folder name plus
a document inside it.

Four consequences, and every one of them cost something:

1. **Identity is a magic string in a path.** `characters/<slug>/…` and
   `projects/<slug>/…` make the slug the primary key. So a rename is a tree
   rewrite (`characters/rename.py`), and a run that recorded a path is stranded
   by it — which is the whole reason `domain/rewrite.py` exists, and why #420 is
   open. `paths.py` is 300 lines of string construction whose only job is
   keeping every module's spelling of that magic string identical.

2. **Records are documents in a bucket, so nothing can query them.** "Every run
   using this character" is `runs find --character`, which lists every project,
   lists every run in each, reads `request.json` for each, and greps. "Which
   projects involve this character" has no answer at all. Both are one query
   against a row.

3. **Filenames carry structure too.** `<slug>_<group>_<n>.png` in a character's
   reference pool, `<slug>_in_<n>.png` in a project's input pool. Reference
   *order* is filename order, so `curate renumber` and `curate regroup` exist to
   maintain numbering that a row would carry as an attribute. The bible then
   describes those files in a `references:` map keyed on the very basename the
   renumbering changes — which is why the two go out of step and why every
   description write rewrites the whole document.

4. **The web app cannot present any of it.** `WEB_APP.md` states, correctly,
   that the run JSON is deliberately never parsed — the pipeline owns its shape.
   The result is that studio.andreas.services can only ever be a file browser
   over a library whose meaning it is forbidden to read. A character is a folder
   with a YAML file in it; a run is a folder with three JSON files in it.

The bucket also **leaks names**, which is a hard-rule-#1 problem hiding in
plain sight: a listing of the media bucket is a list of character slugs. The
repo forbids naming a character in code, docstrings, fixtures and commit
messages, and then writes every one of them into an S3 key.

**The fix in one line:** characters, projects, runs, scenes and movies become
rows with UUIDs; the folder tree stays exactly what it is and hangs off them;
S3 keys carry ids and never names.

---

## Principles

1. **An id is the identity. A slug is a label.** Every entity has a `v4` UUID
   that never changes. The slug is a mutable, library-unique attribute. Renaming
   is one conditional write and touches nothing else, ever.
2. **No name in any S3 key.** Keys are built from ids and are opaque —
   stamped once at creation, never parsed, never re-derived.
3. **Every mutation is an API route.** The CLI holds no AWS credentials and
   composes no writes of its own; it calls the same routes the SPA calls. This
   was already true for bytes ([#308](#), #302) and is now true for records.
4. **Structured data belongs in the row; opaque payloads belong in a blob.**
   Studio owns the envelope of a run and validates it; the model provider owns
   the request and response bodies, which studio stores and never parses. The
   present rule ("do not decode `request.json`") survives, moved to where it is
   actually true.
5. **The file tree is not replaced.** Every entity owns a folder node. Browse,
   upload, create, rename, move, copy and delete work inside it exactly as they
   do today. Nothing about the file layer's user-facing behaviour changes.
6. **One addressing scheme: the node id.** Name paths and raw keys both go.

---

## Decisions — all five settled, all five built

This section asked for five answers before any code moved. Every one was
answered **as recommended** and every one has shipped, so what stood here as a
choice is recorded here as an outcome. The reasoning that produced each is in
the git history of this file; the consequences are the rest of this document.

| | Question | Settled on | Where it lives now |
|---|---|---|---|
| **D1** | One table or three? | **One.** `studio-<env>-catalog` gained `CHAR#`, `PROJ#`, `RUN#`, `SCENE#`, `MOVIE#` partitions beside `LIB#`, `USER#` and `NODE#`. | [Item table](#item-table) |
| **D2** | What an S3 key looks like | **`<owner_kind>/<owner_id>/<node_id>.<ext>`** — carries the owner's id, carries no name. Stamped once at creation, never parsed, never re-derived. | [S3 layout](#s3-layout) |
| **D3** | How far it goes | **All five entity types**, not characters and projects alone. | [Entities](#entities) |
| **D4** | Prod data | **Migrated**, by a forward migrator: `plan` / `apply` / `verify` as separate invocations, journalled under `local/migrations/`. | `maintenance/catalog_migrate.py` |
| **D5** | Entities in the reel | **Sparse `by-recent`**, re-keyed on a `reel` attribute written only onto image and video file nodes. Fixed the pre-existing folder pollution on the way past. | [Item table](#item-table) |

**D2's honest cost is still live and is not a defect.** Moving a file between
entities leaves the old prefix on its key. The key stays correct — it is a
pointer, not a name — it just stops looking like it means anything.
`studio catalog verify` reports the drift and `studio catalog reseat --apply`
rewrites it: server-side copy, row update, delete of the old object. Optional,
out of band, never automatic, and it refuses until a `verify` has passed.

**D4 is done and the migrator is not.** `plan`, `apply` and `verify` ran against
production; `reseat` has not, so prod's keys are the legacy ones D2 replaced and
`verify` reports them as drifted rather than broken. The module stays for
`reseat`, and because `verify` is what gates it.

## The data model

One table (D1), all five entity types (D3).

### Entities

```
Library    lib-…      the sharing unit; has members
 ├ Node    node-…     a folder or a file, with a parent
 ├ Character char-…   who a subject is
 ├ Project  proj-…    a unit of production
 ├ Run      run-…     one submission to a model
 ├ Scene    scene-…   shots stitched into one continuous take
 └ Movie    movie-…   scenes cut into one piece
```

Ids are `<kind>-<uuid4>`. The prefix is for a human reading a log; nothing
parses it.

### Item table

| Item | `pk` | `sk` | Why |
|---|---|---|---|
| Library | `LIB#<lib>` | `META` | exists |
| Membership | `USER#<sub>` | `LIB#<lib>` | exists |
| Node — by parent | `NODE#<parent_id>` | `NAME#<name>` | exists |
| Node — by id | `NODE#<node_id>` | `META` | exists |
| **Character** | `CHAR#<char_id>` | `META` | the record |
| **Character slug claim** | `LIB#<lib>` | `CHARSLUG#<slug>` | uniqueness, and the list-characters query |
| **Reference entry** | `CHAR#<char_id>` | `REF#<node_id>` | one row per reference image |
| **Project** | `PROJ#<proj_id>` | `META` | the record |
| **Project slug claim** | `LIB#<lib>` | `PROJSLUG#<slug>` | uniqueness, and the list-projects query |
| **Project ↔ character** | `PROJ#<proj_id>` | `CHAR#<char_id>` | involvement; reverse-queryable |
| **Run** | `RUN#<run_id>` | `META` | the envelope |
| **Run in project** | `PROJ#<proj_id>` | `RUN#<created>#<run_id>` | list a project's runs, newest first, paginated |
| **Run ↔ character** | `RUN#<run_id>` | `CHAR#<char_id>` | which characters a run used |
| **Scene** | `SCENE#<scene_id>` | `META` | |
| **Scene in project** | `PROJ#<proj_id>` | `SCENE#<created>#<scene_id>` | |
| **Shot** | `SCENE#<scene_id>` | `SHOT#<shot_id>` | one row per planned shot |
| **Movie** | `MOVIE#<movie_id>` | `META` | |
| **Movie in project** | `PROJ#<proj_id>` | `MOVIE#<created>#<movie_id>` | |
| **Phrasebook term** | `LIB#<lib>` | `TERM#<model>#<avoid>` | the wording lists, finally a table |

**Two items per entity, for the same reason a node is two items.** The `META`
row is the record; the claim / membership row is what makes the entity listable
and its slug unique. Every create, rename and delete is one
`TransactWriteItems`, and a slug collision is a condition failure on
`attribute_not_exists(pk)` — never a read-then-write.

**No new GSI is required.** Listing a library's characters is
`query(pk=LIB#<lib>, begins_with(sk, "CHARSLUG#"))` followed by a
`BatchGetItem` over the `CHAR#…/META` rows — the exact shape `GET /api/nodes`
already uses, and for the same reason: the claim row stays a pointer rather than
a projection nobody has to keep in step. `by-sk` answers the reverse questions
(`sk = CHAR#<id> AND begins_with(pk, "RUN#")` is "every run using this
character"), which is why that index stops having one script as its only
consumer.

### Why an entity is two items

The same two reasons a node is two items, and it is worth stating rather than
inheriting silently.

DynamoDB enforces uniqueness on **one thing only: the primary key**. So the two
properties an entity needs pull in opposite directions:

- The record must be keyed on the **id**, because the id is what every other row
  points at and it must never change. `CHAR#<char_id>` / `META`.
- The slug must be **unique in the library**, and the only way to say that to
  DynamoDB is to make the slug part of a key. `LIB#<lib>` / `CHARSLUG#<slug>`,
  written under `attribute_not_exists(pk)`.

One item cannot be keyed both ways, so there are two. The claim item then earns
its keep a second time: it is also the **list index**. `every character in this
library` is `query(pk = LIB#<lib>, begins_with(sk, "CHARSLUG#"))` — one query.
Without it, that question is a `Scan` with a filter, which is the one access
pattern this table must never have.

**A GSI does not substitute for it.** An index hashed on `lib` and ranged on
`slug` would give the listing, but a GSI enforces nothing: two records with the
same slug both land in it, silently. Uniqueness has to be a condition
expression on a real key.

**Keying the character on its slug instead** — `LIB#<lib>` / `CHAR#<slug>` —
collapses it to one item and reintroduces exactly the disease: renaming becomes
delete-and-recreate, and every `REF#` row, run link and binding that pointed at
it is pointing at a key that no longer exists.

So: two items, one transaction, and the create/rename/delete paths are the same
shape as the node writes beside them. A rename is: delete the old claim, put the
new claim conditionally, update the record, rename the root folder node — four
operations, atomic.

### The folder layout is convention, not schema

**An entity record holds exactly one node id: `root`.** It does not enumerate
`reference/`, `corpus/`, `runs/`, `input/` or anything else.

An earlier draft of this spec put a five-key `folders` map on each record. That
was wrong on three counts:

1. **It is derived state.** The folders are children of `root` and are found by
   one `GetItem` on `NODE#<root>` / `NAME#reference`. Storing their ids caches a
   lookup that costs one read.
2. **It goes stale, and the file layer is what breaks it.** A person can rename
   `reference/`, move it, or delete it — those are ordinary file operations and
   they must stay ordinary. A stored map would then point at a folder that has a
   different name, a different parent, or no existence.
3. **It is rigid where the product is not.** People make their own folders. A
   model that enumerates five blessed ones implies the other twelve are
   second-class, and they are not.

**What replaced the map is the fact that pools stopped being structural.** Today
`reference/` is load-bearing because reference-ness is *inferred from the path* —
which is the coupling this whole document removes. Once a reference is a `REF#`
row, an image is identity because a row says so, **not because of which folder it
sits in**. `corpus/`, `seed/` and `archive/` were never anything but folders with
conventions attached; they can now be exactly that.

So the layout lives in **one constant in the API**, applied at creation and
never recorded:

```python
# services/layout.py — convention. Nothing depends on it existing afterwards.
CHARACTER_LAYOUT = ("reference", "corpus", "seed", "archive")
PROJECT_LAYOUT   = ("runs", "scenes", "movies", "chains", "input")

RUN_PARENT   = "runs"      # where POST /api/runs puts a new run's folder
SCENE_PARENT = "scenes"
MOVIE_PARENT = "movies"
INPUT_FOLDER = "input"     # what GET /api/projects/<id>/inputs reads
```

Creating a character creates those four folders **as a starting layout**, because
an empty character is unhelpful. Nothing afterwards requires them.

**Resolution is by name, at write time, and self-healing.** `POST /api/runs`
resolves `runs` under the project's root and creates it if it is absent. If
someone renamed `runs/` last week, a new one appears and **every existing run is
still perfectly reachable**, because a run record names its own folder node id
(`folder`) rather than a path. The same is true of scenes, movies and the input
pool. A route that cannot find its conventional folder makes one; it never
fails, and it never guesses.

**The one hard rule this leaves:** a folder that is some entity's `root` cannot
be deleted while the entity exists. `DELETE /api/nodes` refuses it and says which
entity to delete instead.

**The reverse pointer.** The root folder node carries `entity: "char-9f3c…"`,
written once in the create transaction and never changed. It is what lets a
listing draw a character card instead of a folder icon, and what
`GET /api/nodes/<id>/owner` walks up to. One attribute in each direction; no map
in either.

### Character record

```jsonc
{
  "id": "char-<uuid>",
  "lib": "lib-<uuid>",
  "slug": "<slug>",                 // library-unique, mutable, [a-z0-9_-]
  "display_name": "<Name>",
  "fictional": true,                // the consent question; unchanged in meaning
  "rev": 7,                         // optimistic concurrency; see below
  "created": "…", "updated": "…",
  "root": "node-…",                 // the ONE pointer into the tree
  "hero": "node-…",                 // the card image; any reference node
  "default_set": ["node-…", "node-…"],
  "profile": { … }                  // the bible, as a validated map
}
```

`profile` is the whole of today's `profile.yaml` minus `name`, `display_name`
and `fictional`, which are promoted to real fields, and minus `references:` and
`default_set:`, which become rows. The remaining sections — `identity`, `face`,
`body`, `wardrobe`, `voice`, `rendering`, `consistency`, `text_identity_block` —
are stored as nested maps and validated against a schema the API owns.
`schema_version` moves onto the record.

**`rev` closes a window that is currently open.** Today `write_profile` re-reads
the node's `updated_at` and refuses if it moved — check-then-write, with a gap.
A `ConditionExpression` on `rev` is compare-and-swap, and `PIPELINE.md`'s note
that "closing that window needs an `If-Match` on the API" is satisfied by it.

### Reference entry

```jsonc
{
  "pk": "CHAR#<char_id>", "sk": "REF#<node_id>",
  "group": "face",                  // face | body | frame | wardrobe | …
  "order": 3000,                    // gapped by 1000; a reorder is one write
  "description": "…",               // what the bible's `references:` map held
  "tags": ["…"],
  "created": "…"
}
```

**This is what kills filename magic.** Order is an attribute, not a trailing
number, so `curate renumber` has nothing to maintain. Group is an attribute, so
`curate regroup` becomes one `PATCH`. A description is one row's write, so two
descriptions written at once stop fighting over one document. A reference image
can be called anything.

**Slot N stays "position N in the resolved selection"** — the definition does
not change, but resolution moves into the API
(`GET /api/characters/<id>/selection`) so the CLI and the SPA cannot disagree
about what a model was shown.

### Project record

```jsonc
{
  "id": "proj-<uuid>", "lib": "lib-<uuid>",
  "slug": "<slug>", "title": "…", "description": "…",
  "rev": 3, "created": "…", "updated": "…",
  "root": "node-…",
  "hero": "node-…",
  "counts": { "runs": 41, "scenes": 3, "movies": 1 }   // maintained, not scanned
}
```

Characters involved are `PROJ#<id>` / `CHAR#<id>` rows, not a list on the
record — so the reverse question is answerable and a character delete can find
what points at it.

### Run record

```jsonc
{
  "id": "run-<uuid>", "lib": "…", "project": "proj-…",
  "slug": "<slug>",                 // human label; no longer an id
  "status": "pending|running|succeeded|failed|cancelled",
  "kind": "image|video",
  "engine": "…", "model": "google/nano-banana-pro",
  "prediction_id": "…",
  "created": "…", "submitted": "…", "completed": "…",
  "bindings": { "image": ["node-…"], … },   // NODE IDS, never URLs, never paths
  "characters": ["char-…"],                  // also written as rows
  "folder": "node-…",                        // the run's own folder
  "outputs": ["node-…", …],
  "lineage": { "from_run": "run-…", "from_output": "node-…" },
  "cost": { "currency": "USD", "amount": 0.032 },   // when the provider reports it
  "error": null,
  "payload": { "request": "node-…", "response": "node-…", "prompt": "node-…" }
}
```

**`payload` names nodes, and studio never decodes what is in them.** Hard rule
#3 moves with the bindings: they are node ids now, and a URL-shaped binding is
refused by the API rather than by `runs.py` — which is a strengthening, because
the API is the only thing both halves of studio go through.

Scene and movie records follow the same shape: an envelope of ids and status,
with shots as `SHOT#` rows carrying `order`, `prompt`, `run`, `panel`, and the
stitched output as a node id.

### What is deleted from the model

- Every `*_prefix()` / `*_key()` builder in `domain/paths.py` for characters and
  projects. The module becomes a name-validation helper or disappears.
- `domain/rewrite.py` in its entirety, and #420 with it. A record names a node
  id; a rename or a move cannot strand one. **This is the single largest
  simplification in the proposal.**
- `domain/characters/rename.py` — a rename is `PATCH /api/characters/<id>`.
- `curate renumber` and `curate regroup`.
- The name-path write routes (`/api/folder`, `/api/object`, `/api/objects/*`,
  `PATCH /api/text?key=`) and `GET /api/asset?key=` — see
  [Shared material](#shared-material).
- `services/keys.py`'s `clean_key`, `_normalise`, `_reject_traversal`.

---

## S3 layout

Assumes D2 = entity-prefixed keys.

```
characters/<char_id>/<node_id>.<ext>     bytes owned by a character
projects/<proj_id>/<node_id>.<ext>       bytes owned by a project (runs, scenes, movies, inputs)
libraries/<lib_id>/<node_id>.<ext>       bytes under the library root, owned by neither
```

Three prefixes and nothing else. No `blobs/`, no `phrasebook/`, no `config/`, no
slug anywhere.

**The owner is derived, not stored.** A node's `path` is already the
materialised list of ancestor ids; each library keeps a small map of
entity-root node id → entity, so the owner of any node is a lookup against its
ancestors. Nothing new is written, nothing drifts, and a move that changes the
owner is visible immediately even though the key it stamped is not rewritten.

**What the tree looks like to a person** is unchanged, because the tree is the
catalog's and always was:

```
<character>/                 ← a folder node the character record names
├── reference/  corpus/  seed/  archive/
<project>/                   ← a folder node the project record names
├── runs/<run slug>/         ← the run record names this folder
│   ├── request.json  result.json  prompt.json    ← payload blobs
│   └── output/
├── scenes/  movies/  chains/  input/
```

Folders a person makes by hand keep working and belong to nobody in particular.

### Shared material

`phrasebook/wording.yaml` and `config/pose/` are the two things with no catalog
node today, and they are the sole reason `GET /api/asset?key=` still takes a raw
S3 key.

- **The phrasebook becomes rows** — `LIB#<lib>` / `TERM#<model>#<avoid>`. It is
  a per-model list of avoid/use pairs, which is a table wearing a YAML file.
  `phrasebook add` stops being able to fail on a library that has never held the
  document, because there is no document.
- **Pose plates become nodes** in a `config/` folder created with the library and
  populated through the API by `dev-setup.sh` / the deploy. Their source of
  truth stays the repo.

Both then have node ids, `store.shared_read` / `shared_presign` collapse into
the ordinary calls, and `?key=` is deleted. **One addressing scheme, no
exceptions.**

---

## API

Every route is library-scoped by `X-Studio-Library` exactly as today, and every
entity response is membership-checked against the entity's own `lib`. Slugs are
accepted only where noted; everything else takes ids.

### Characters

| Route | Body / params → result |
|---|---|
| `GET /api/characters` | `?q=` → `[{id, slug, display_name, hero, counts, updated}]` |
| `POST /api/characters` | `{slug, display_name, fictional, profile?}` → **201** the record. Creates entity + slug claim + root + four pool folders in one transaction. **409** on slug |
| `GET /api/characters/<id>` | the full record, `profile` included. `<id>` may be `slug:<slug>` |
| `PATCH /api/characters/<id>` | `{slug?, display_name?, fictional?, hero?, rev}` → **409** on a stale `rev`, **409** on a taken slug |
| `PUT /api/characters/<id>/profile` | `{profile, rev}` → whole-bible replace, validated. The `edit` round trip |
| `PATCH /api/characters/<id>/profile` | `{patch, rev}` → merge one section |
| `DELETE /api/characters/<id>` | `?files=keep\|delete` — refuses while a project or run still links it, unless `?force=1` |
| `GET /api/characters/<id>/references` | `?group=` → entries in `(group, order)` order, each with its node and a presigned URL |
| `POST /api/characters/<id>/references` | `{node, group, description?, tags?, after?}` → attaches an existing node. **409** if already a reference |
| `PATCH /api/characters/<id>/references/<node>` | `{group?, description?, tags?, after?}` |
| `PUT /api/characters/<id>/references` | `{entries: [{node, group, description?, tags?}]}` → bulk describe / reorder in one transaction. This is `describe-refs` and `sync-refs` |
| `DELETE /api/characters/<id>/references/<node>` | detaches; the file stays where it is |
| `PUT /api/characters/<id>/default-set` | `{nodes: [...]}` |
| `GET /api/characters/<id>/selection` | `?pick=&tag=&limit=` → the ordered nodes a model would be shown, with presigned URLs. **Refuses** an over-cap selection with the index in the body — the current behaviour, moved to one place |
| `GET /api/characters/<id>/textblock` | the pasteable identity paragraph |
| `GET /api/characters/<id>/runs` | `?cursor=` → runs that used this character, newest first |
| `GET /api/characters/<id>/projects` | projects that involve it |

### Projects

| Route | Body / params → result |
|---|---|
| `GET /api/projects` | `[{id, slug, title, hero, counts, updated}]` |
| `POST /api/projects` | `{slug, title?, description?, characters?}` → **201**. Creates entity + claim + root + five subfolders |
| `GET /api/projects/<id>` | record; `<id>` may be `slug:<slug>` |
| `PATCH /api/projects/<id>` | `{slug?, title?, description?, hero?, rev}` |
| `DELETE /api/projects/<id>` | `?files=keep\|delete`; refuses while it holds runs unless `?force=1` |
| `PUT /api/projects/<id>/characters` | `{characters: [id, …]}` → replaces the involvement links |
| `GET /api/projects/<id>/inputs` | the working pool, name-ascending natural sort. **Position in this list is `--input N`** |
| `GET /api/projects/<id>/runs` | `?status=&model=&character=&cursor=` |
| `GET /api/projects/<id>/scenes` · `/movies` | listings |

### Runs, scenes, movies

| Route | Body / params → result |
|---|---|
| `POST /api/runs` | `{project, kind, engine, model, slug, input, bindings, characters?, prompt?}` → **201** `{id, folder, payload}`. Creates run + project link + character links + folder + payload blobs. **Refuses a URL-shaped binding** |
| `GET /api/runs` | `?project=&character=&model=&status=&since=&cursor=` — the query that replaces `runs find` |
| `GET /api/runs/<id>` | envelope + output nodes + lineage |
| `PATCH /api/runs/<id>` | `{status, prediction_id?, error?, cost?, completed?}` |
| `POST /api/runs/<id>/outputs` | `{name, size, content_type}` → a node under the run's `output/` and a presigned PUT |
| `POST /api/runs/<id>/response` | `{body}` → stores the provider response as a payload blob |
| `DELETE /api/runs/<id>` | `?files=keep\|delete` |
| `POST /api/scenes` | `{project, slug, title, shots: [...]}` → **201** |
| `GET /api/scenes` · `GET /api/scenes/<id>` · `PATCH` · `DELETE` | as above |
| `PUT /api/scenes/<id>/shots` | `{shots: [...]}` → the plan revision; merges onto rendered work rather than replacing it |
| `PATCH /api/scenes/<id>/shots/<shot_id>` | `{run?, panel?, prompt?, order?}` |
| `POST /api/scenes/<id>/output` | `{name, size, content_type}` → upload URL for the stitched take |
| `POST /api/movies` · `GET` · `PATCH` · `DELETE` · `PUT /api/movies/<id>/scenes` | the tier above |

**Stitching stays in the CLI.** `ffmpeg` ships in the pipeline wheel and the
Lambda has none; `assemble` downloads, stitches locally, uploads the result and
`PATCH`es the record. The API owns the record, not the encode.

### Phrasebook

| Route | |
|---|---|
| `GET /api/phrasebook` | `?model=` → terms |
| `POST /api/phrasebook` | `{model, avoid, use, note?}` → **201**; **409** on a duplicate pair |
| `DELETE /api/phrasebook/<model>/<avoid>` | |

### Nodes — the file layer, ids only

Kept, with the name-path routes removed and the bulk verbs moved onto ids.

| Route | |
|---|---|
| `GET /api/nodes?parent=` · `GET /api/nodes/<id>` · `GET /api/resolve?path=` | unchanged |
| `POST /api/nodes` `{parent, name, kind, on_conflict?}` | unchanged |
| `PATCH /api/nodes/<id>` `{name}` **or** `{parent}` | unchanged; both is still a 400 |
| `POST /api/nodes/move` `{ids, destination}` | replaces `/api/objects/move` and `/api/folder/move` |
| `POST /api/nodes/copy` `{ids, destination}` | replaces `/api/objects/copy` |
| `DELETE /api/nodes` `{ids}` | replaces `/api/objects` and `/api/folder` |
| `GET/PATCH /api/nodes/<id>/text` | replaces `/api/text` in both directions |
| `GET /api/nodes/<id>/download-url` · `POST /api/nodes/<id>/upload-url` · `/confirm-upload` | unchanged |
| `GET /api/tree?node=` · `GET /api/reel?node=` | `prefix=` dropped |
| `GET /api/nodes/<id>/owner` | which entity a node belongs to, derived from its ancestry — what the SPA shows as "in project …" |

**A node view gains `owner`**: `{kind, id, slug}` or null. It still never carries
`blob_key` or `path`.

---

## CLI

The command surface stays recognisable — the same verbs, taking slugs, calling
the API. What changes is that nothing composes a path and nothing writes a
document.

```
session     login · logout · whoami                                unchanged

generate    run · models · add-model                               --project takes a slug or an id
            run now records bindings as node ids

records     runs      list · show · find · outputs · adopt         list/find are one API query
            scenes    new · list · show · plan · board · render · check · handoff · assemble · sheet · outputs
            movies    new · list · show · outputs
            frames    at · last · grid · chain
            projects  list · new · show · edit · rename · delete · link · unlink
                      inputs · add-inputs

characters  character list · create · show · edit · set-profile · rename · delete
                      refs · add-refs · describe-refs · set-ref-desc · sync-refs
                      order · regroup · default-set · textblock · shoot
                      pool · add-to
            curate    dedupe · groups · move
            contact-sheet

authoring   prompt · phrasebook (add · show · terms · models · check · rm)

objects     upload · download · presign · convert

maintenance catalog (plan · migrate · verify · gc · reseat) · dev-seed
```

### What changes, command by command

| Command | Change |
|---|---|
| `character create <slug>` | `POST /api/characters`. Creates the pools as part of the transaction rather than lazily on first write |
| `character rename <slug> <new>` | one `PATCH`. **No objects move, no records are rewritten, nothing can be stranded.** Today this is a per-basename `PATCH` sweep plus a record rewrite |
| `character set-ref-desc` / `describe-refs` | one row write each, or one bulk `PUT`. No whole-bible rewrite, no `updated_at` conflict dance |
| `character order <slug> --group face <node>…` | **new** — explicit reference ordering, replacing filename numbering |
| `character regroup` (was `curate regroup`) | one `PATCH` per entry; no object moves |
| `curate renumber` | **deleted** — nothing to renumber |
| `curate move` | a node move, unchanged in meaning |
| `projects new <slug>` | `POST /api/projects` |
| `projects link <slug> <character>` | **new** — maintain involvement explicitly |
| `projects rename` | **new**, and trivial — it was impossible before |
| `runs find --character <slug>` | one API query instead of a walk over every project |
| `runs list --model --status --since` | **new** filters, free from the row |
| `runs show` | prints the envelope; `--payload` prints the untouched provider documents |
| `rewrite check` | **deleted** — the class of bug is gone |
| `phrasebook add` | `POST /api/phrasebook`; no document to be missing |
| `upload` / `download` / `presign` | take a node id or a `<entity>/<path>` address that the API resolves |
| `catalog migrate` | the D4 migrator — `plan` / `apply` / `verify`, run against prod |
| `catalog reseat` | rewrite blob keys whose owner prefix has drifted — not yet run against prod |

**Addressing on the command line.** A slug is still what a person types.
`<slug>/reference/face/<file>` resolves through
`GET /api/resolve?path=` against the character's root — so the strings in every
`SKILL.md` keep working as *addresses* while ceasing to be *keys*. Ambiguity
between a character and a project called the same thing is settled by the
command: `studio character …` resolves in characters, `studio projects …` in
projects, and `--project` never looks at characters.

---

## The web app

Today the SPA is a file browser rooted at the library, and the entity structure
is invisible to it. The new shell puts entities first and keeps the browser
reachable from everywhere.

### Routes

| URL | Screen |
|---|---|
| `/` | Home — Characters, Projects, and Recent (the reel) |
| `/c/<char_id>` | Character page |
| `/p/<proj_id>` | Project page |
| `/p/<proj_id>/r/<run_id>` | Run page |
| `/s/<scene_id>` · `/m/<movie_id>` | Scene, Movie |
| `/f/<node_id>` · `/o/<node_id>` | Folder browser, object viewer — unchanged |

Ids in URLs everywhere, so every link survives every rename. No legacy
redirect route; `LegacyRedirect.tsx` goes.

### Character page

Tabs: **Profile · References · Corpus · Seed · Archive · Files**

- **Profile** renders the bible as fields, editable in place, saved with `rev`.
  Not a textarea over YAML — the shape is studio's now, so it can be a form.
- **References** is a grid grouped by purpose, with drag-to-reorder writing
  `order`, inline descriptions, tag filters, and a visible marker on the
  `default_set`. The engine caps (Kling 7, Seedance 9, Nano Banana 14) are shown
  against the current selection, so an over-cap set is visible before a shoot
  refuses it.
- **Corpus / Seed / Archive** are file grids over whatever folders the
  character actually has — the existing browse components, scoped. The tabs are
  built from the root's children, not from a fixed list, so a folder someone
  made themselves gets a tab like any other.
- **Files** is the raw browser at the character's root: create, upload, rename,
  move, copy, delete, exactly as today.

### Project page

Tabs: **Overview · Runs · Scenes · Movies · Inputs · Files**

- **Runs** is the screen that does not exist today: a filterable list — model,
  status, character, date — each row showing its output thumbnail, model, cost
  and lineage. A run opens to its envelope, its outputs, its chain, and its
  payload documents as raw text (still never parsed).
- **Scenes / Movies** show the plan, the shots and the cut.
- **Inputs** is the working pool with positions shown, because `--input N` is a
  position.
- **Files** is the raw browser at the project's root.

Everything is built from `@ansavva/design-system` per the repo rule; the
`design-system-ui` skill is read before the first screen.

### What survives untouched

Reel, the object viewer, video scrubbing, keyboard navigation, upload,
selection, the library switcher, and every file operation. This is additive to
the browsing experience, not a replacement for it.

---

## Migration

Assumes D4 = migrate.

`studio catalog migrate plan | apply | verify`, then `reseat` — separate
invocations, `--dry-run` unless `--apply`, journalled under
`local/migrations/<ts>.json`, in the shape `catalog_seed` established and for
the same reason: the ordering between phases is the safety property.

| Phase | Does |
|---|---|
| `plan` | Walks the catalog. Reports every character, project, run, scene and movie it would create, every document it would parse, and every one it cannot. **UNPARSEABLE must be 0** before `apply` |
| `apply` | Creates entity rows; adopts each existing tree's top folder as the entity's `root` rather than making a new one; turns each `references:` entry into a row; turns each run/scene/movie document into an envelope and leaves the document in place as its payload blob. **Copies no bytes, moves no objects, deletes nothing** |
| `verify` | Re-reads both sides: every entity resolves, every folder it names exists, every reference names a live node, every envelope's outputs exist |
| `reseat` | *Optional, separate, later.* Rewrites blob keys to the new scheme — server-side copy, row update, delete of the old object. Only after `verify` passes |

Slugs are read off the existing folder names and become the entity's `slug`
attribute — so the strings a person types do not change on migration day even
though nothing is addressed by them any more.

### Running it, per environment

**Prod — migrate BEFORE deploying.** `apply` only adds rows, and every one of
them is invisible to the code currently running: entity rows carry
`created`/`updated` rather than `created_at`, so they do not enter the present
`by-recent` index, and their `pk` prefixes keep them out of every node listing.
The `reel` stamps sit inert until the GSI is re-keyed. So there is no window in
which prod is half-migrated and visibly wrong.

```bash
studio catalog migrate plan       # UNPARSEABLE must be 0, or apply refuses
studio catalog migrate apply
studio catalog migrate verify
studio config sync --apply        # the pose plates, which have no node in prod
# then merge: studio-prod.yaml applies the GSI and ships the new image
studio catalog reseat --apply     # optional, later, never automatic
```

Deploying first also works and costs a **degraded window**: from the moment
`deploy-infra` re-keys `by-recent`, the reel is blank — no row carries `reel`
yet — and the entity pages are empty until `apply` runs. File browsing is
unaffected, because nodes do not change.

**`studio config sync` is not optional in prod.** The plates have been objects
with no node since before the catalog, and `catalog_seed` deliberately recorded
none for them. Every shoot refuses until they have rows. The old objects are
left where they are and become collectable by `catalog gc`.

**How the CLI is pointed at prod is an open question, not a step.** The migrator
is one of the maintenance commands that opens AWS clients directly rather than
going through the API, so running it against prod means naming the prod table
and bucket under a real `aws login` — which is exactly the mechanism
[studio/CLAUDE.md](../CLAUDE.md) records as wanted and undecided. Decide it
before migration day; do not improvise it on the night.

**Dev stacks — no migration.** A stack holds the pose plates and nothing else,
so there is no character, project or run to raise a row over. What each needs is
the re-keyed GSI and the plates as nodes:

```bash
./studio/scripts/dev-aws-setup.sh     # applies the GSI change
./studio/scripts/dev-setup.sh         # pushes the plates through the API
```

Given there is nothing to preserve, `dev-aws-destroy.sh` and re-provision is
cheaper and has fewer states to reason about. Either way this is **per machine**:
a stack is keyed to a persistent machine id, so it cannot be done centrally, and
a stack whose id is lost keeps billing while being unreachable.

**The seed fixture** — `publish` has still never been run, so there is nothing
there to migrate.

---

## Build order

Each phase is a PR, green on its own, and the service keeps working throughout.

| # | Phase | Contains |
|---|---|---|
| 1 | **Catalog service** | New item shapes, entity CRUD, slug claims, `rev`, transactions, unit tests. No routes yet |
| 2 | **Characters + projects API** | Routes above, `moto`-backed tests both sides, smoke coverage |
| 3 | **CLI onto entities** | `character`, `projects`, `curate` move to the API; `paths.py` character/project builders and `rename.py` deleted; CLI surface reference regenerated deliberately |
| 4 | **Runs typed** | `POST /api/runs` gains the envelope; `runs.py` records ids; `rewrite.py` and `runs find`'s walk deleted |
| 5 | **Scenes + movies typed** | Same, one tier up |
| 6 | **SPA — entities** | Home, character page, project page, run page; browser rescoped, `LegacyRedirect` deleted |
| 7 | **Shared material** | Phrasebook rows, pose plates as nodes, `?key=` and `keys.clean_key` deleted |
| 8 | **Migrator** | `catalog migrate`, then `reseat` |
| 9 | **Sweep** | Name-path routes deleted, docs rewritten, `PIPELINE.md` and `WEB_APP.md` reconciled against this file |

Phases 1–3 are the ones that answer your complaint directly. 4–5 are D3. 6 is
the presentation rethink. 7–9 are the cleanup that makes the model honest.

---

## Open questions beyond the five decisions

1. **Does a character belong to exactly one library?** Assumed yes. A character
   shared across libraries would need a copy or a link table; nothing wants one
   yet.
2. **Should `run` carry cost?** Replicate reports prediction metrics
   inconsistently by model. Proposed: record it when the provider gives it, and
   never compute it.
3. **Delete semantics.** Proposed: deleting an entity defaults to keeping its
   files (the folder is orphaned into the library root) and `?files=delete` is
   explicit. The reverse default loses media to a typo.
4. **`chains/`** — an ad-hoc frame sequence with no scene behind it. Proposed:
   leave it as an ordinary folder for now rather than making it a sixth entity.
