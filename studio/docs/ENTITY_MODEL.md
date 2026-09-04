# studio — the entity model

> **STATUS: BUILT. This is the reference.** It was a proposal, and its own
> header said so until the last of it shipped; that line is replaced rather than
> kept, because a spec that says "nothing here is built" over a model the whole
> service now runs on is worse than no status at all.

> **ONE PART OF IT IS SUPERSEDED: the reference entry.** This document
> introduced `CHAR#<id>` / `REF#<node>` — one row per reference image, carrying
> `group` and `order` — and argued for it well: reference-ness stopped being
> inferred from a path, which is what let a file be renamed and moved without
> changing what it is. What it did not fix is that the fact still lived *beside*
> the picture rather than *on* it, and `default_set` on the record made two
> homes for one question. The invariant between them drifted: one production
> character carried four ids in `default_set` naming no row, and a default shoot
> sent three images where seven were meant.
>
> **It is a tag on the file now** — `default` for the images a generation is
> shown, `face` or `body` for what the picture is — and the rows are deleted.
> Every `REF#` and `default_set` passage below is history: the reasoning is
> worth keeping because the second half of it is what tags finish, and rewriting
> it would erase why the row existed at all.

Read [What was wrong](#what-was-wrong-and-what-this-replaced) for the shape
this replaced, then go to [The data model](#the-data-model). The five decisions
it turned on are settled and recorded in
[Decisions](#decisions--all-five-settled-all-five-built); nothing below is
conditional on anything any more.

---

## Principles

1. **An id is the identity. A name is a label.** Every entity has a `v4` UUID
   that never changes. The name is a mutable free-text attribute: **not unique,
   not claimed, and nothing resolves an entity by it.** Renaming is one
   conditional write on one row and touches nothing else, ever.

   This principle used to read "a slug is a label" and then contradict itself:
   a slug was library-unique, claimed by a conditional write, and an address the
   API resolved — which is not what a label is. Slugs are gone, `display_name`
   and a project's `title` collapsed into the same `name`, and every address is
   an id.
2. **No NAME in any S3 key, and no key is ever parsed.** A key is
   `<owner_kind>/<owner_id>/<node_id><ext>` and stops there — three segments, so
   a listing names no character, no project and no file. It is stamped once at
   creation and never re-derived. See
   [D2, and the descriptive detour](#d2-and-the-descriptive-detour).
3. **Every mutation is an API route.** The CLI holds no AWS credentials and
   composes no writes of its own; it calls the same routes the SPA calls, for
   bytes and for records alike.
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
| **Character index** | `LIB#<lib>` | `CHAR#<char_id>` | the list-characters query |
| ~~**Reference entry**~~ | ~~`CHAR#<char_id>`~~ | ~~`REF#<node_id>`~~ | **superseded** — identity is `default` + a group tag on the node |
| **Project** | `PROJ#<proj_id>` | `META` | the record |
| **Project index** | `LIB#<lib>` | `PROJ#<proj_id>` | the list-projects query |
| **Project ↔ character** | `PROJ#<proj_id>` | `CHAR#<char_id>` | involvement; reverse-queryable |
| **Run** | `RUN#<run_id>` | `META` | the envelope |
| **Run in project** | `PROJ#<proj_id>` | `RUN#<created>#<run_id>` | list a project's runs, newest first, paginated |
| **Run ↔ character** | `RUN#<run_id>` | `CHAR#<char_id>` | which characters a run used |
| **Scene** | `SCENE#<scene_id>` | `META` | |
| **Scene in project** | `PROJ#<proj_id>` | `SCENE#<created>#<scene_id>` | |
| **Shot** | `SCENE#<scene_id>` | `SHOT#<shot_id>` | one row per planned shot |
| **Scene ↔ run** | `SCENE#<scene_id>` | `RUN#<run_id>` | which runs a scene's shots bound; reverse-queryable |
| **Movie** | `MOVIE#<movie_id>` | `META` | |
| **Movie in project** | `PROJ#<proj_id>` | `MOVIE#<created>#<movie_id>` | |
| **Movie ↔ scene** | `MOVIE#<movie_id>` | `SCENE#<scene_id>` | which scenes a movie cuts; reverse-queryable |
| **Run ↔ parent run** | `RUN#<run_id>` | `RUN#<parent_id>` | what a run was chained off |
| **Phrasebook term** | `LIB#<lib>` | `TERM#<model>#<avoid>` | the wording lists, finally a table |

### The three row shapes, and which one a relationship gets

Every row above is one of three things. The distinction is not cosmetic — it
decides whether a question has an answer at all, and getting it wrong is silent.

| Shape | Sort key | For | Reverse |
|---|---|---|---|
| **Edge** | `<TARGET>#<target_id>` | set membership | **free** — `by-sk` |
| **Listing** | `<KIND>#<created>#<id>` | chronological pagination | none, and none needed |
| **Ordered child** | `SHOT#<n>` | a positional entity with payload | varies |

**An edge puts the target's id in the SORT KEY, and that is the whole rule.** In
`by-sk` the sort key becomes the hash key, and a hash key takes an exact value
and never a prefix — so a relationship is readable backwards if and only if its
target id is the entire sort key after the prefix. `PROJ#<id>/CHAR#<id>` is; a
listing row's `RUN#<created>#<id>` is not, which costs it a reverse query it
does not need, because a run records its `project` on its own record.

An **ordered child** is an entity in its own right, not a link. A shot exists as
a plan before anything has been rendered into it, so its identity is its
position and the run it may later bind is a field. **Where an ordered child
points at an entity, it gets an edge row beside it**, written in the same
transaction — a link written afterwards is a link a crash can lose.

**Two relationships did not follow this and were only fixed in August 2026.** A
movie's scenes were a JSON list on the record, which no index can address into,
and a scene's run was an attribute on a `SHOT#` row, which `by-sk` cannot see.
So "which movie cuts this scene" and "which scene used this run" had no answer
at any price — the exact complaint this model was built to retire, left standing
for everything except characters. The rule was followed by six edges and written
down nowhere, which is how the two written last came to miss it.

Both kept their original shape and gained an edge beside it, because both carry
something an edge cannot express: a movie may legally cut one scene twice as a
reprise, and an edge is set membership. Every writer maintains its own edges —
`catalog.put_shots` and its siblings.

**Two items per entity.** The `META` row is the record; the second is the
**library index** — `LIB#<lib>` / `CHAR#<char_id>` — which is what makes the
entity listable. It used to be `CHARSLUG#<slug>` and did two jobs, listing and
claiming the name; the claim is gone with slugs, so a create and a delete write
both rows in one `TransactWriteItems` and a **rename touches only the record.**

**No new GSI is required.** Listing a library's characters is
`query(pk=LIB#<lib>, begins_with(sk, "CHAR#"))` followed by a
`BatchGetItem` over the `CHAR#…/META` rows — the exact shape `GET /api/nodes`
already uses, and for the same reason: the index row stays a pointer rather than
a projection nobody has to keep in step. `by-sk` answers the reverse questions
(`sk = CHAR#<id> AND begins_with(pk, "RUN#")` is "every run using this
character"), which is why that index stops having one script as its only
consumer.

### Why an entity is two items

The record is keyed on the **id**, because the id is what every other row points
at and it must never change: `CHAR#<char_id>` / `META`. That answers "read this
character" and answers nothing about "every character in this library" — and
this table must never be scanned — so a second item exists purely as the **list
index**: `LIB#<lib>` / `CHAR#<char_id>`, one query per library.

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

**An entity's root folder is NAMED BY THE ENTITY ID.** It took the slug, so that
somebody browsing the tree saw the name they had chosen — which cannot survive a
free-text name, because a folder's name is unique among its siblings (genuinely:
`child_by_name` resolves a path segment through it) and the second character
called `Anna` would be refused by the tree. That is the uniqueness dropping slugs
was meant to remove, arriving by a side door and with a worse message. So the id
is the folder's name, the way it is already the S3 key's, and a listing hands
back `owner` for an entity root — which is where a client gets a name to draw.

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
  "name": "<Name>",                 // a LABEL: free text, mutable, NOT unique
  "rev": 7,                         // optimistic concurrency; see below
  "created": "…", "updated": "…",
  "root": "node-…",                 // the ONE pointer into the tree
  "hero": "node-…",                 // the card image; any reference node
  "profile": { … }                  // the bible, as a validated map
}
```

`profile` is the whole of today's `profile.yaml` minus `name`, which is promoted
to a real field, and minus `references:` and
`default_set:` — both of which are now tags on the files themselves. The remaining sections — `identity`, `face`,
`body`, `wardrobe`, `voice`, `rendering`, `consistency`, `text_identity_block` —
are stored as nested maps and validated against a schema the API owns.

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
  "name": "…", "description": "…",
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
  "status": "pending|running|succeeded|failed|cancelled",
  "kind": "image|video",
  "engine": "…", "model": "google/nano-banana-pro",
  "prediction_id": "…",
  "created": "…", "submitted": "…", "completed": "…",
  "bindings": { "image": ["node-…"], … },   // NODE IDS, never URLs, never paths
  "characters": ["char-…"],                  // also written as rows
  "folder": "node-…",                        // the run's own folder
  "outputs": ["node-…", …],
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

## S3 layout

Entity-prefixed keys (D2), and nothing below the prefix but the node
([the detour and back](#d2-and-the-descriptive-detour)).

```
characters/<char_id>/<node_id>.<ext>   bytes owned by a character
projects/<proj_id>/<node_id>.<ext>     bytes owned by a project (runs, scenes, movies, inputs)
libraries/<lib_id>/<node_id>.<ext>     bytes under the library root, owned by neither
```

Three prefixes and nothing else. No `blobs/`, no `phrasebook/`, no top-level
`config/`. **Three segments always** — no slug, no folder path, and no filename:

```
characters/char-45f4c2b4-…/node-0304a8b0-….png
projects/proj-a8091a40-…/node-a5e5d2b1-….json
libraries/lib-bf3b86ef-…/node-7c48b0f9-….png
```

The extension is decoration for whoever opens the S3 console; `content_type` on
the row is authoritative and a name with no extension gets a key with none.

**None of the tree is in the key**, and the tree is not diminished by that. The
catalog is the only thing that says what exists and always was: S3 has no
directories, so an empty folder is a node and nothing else, a listing is a
paginated prefix scan where a query on `NODE#<parent>` is one call, and a rename
is a row write rather than a mass copy. The key is a pointer. Never parse it.

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
├── runs/<run id>/           ← the run record names this folder; every entity folder is named by its id
│   ├── request.json  result.json  prompt.json    ← payload blobs
│   └── output/
├── scenes/  movies/  chains/  input/
```

Folders a person makes by hand keep working and belong to nobody in particular.

### Shared material

Nothing in the library lacks a catalog node — the phrasebook and the angle
images included — so nothing is addressed by a raw S3 key.

- **The phrasebook is rows** — `LIB#<lib>` / `TERM#<model>#<avoid>`. It was a
  per-model list of avoid/use pairs, which is a table wearing a YAML file.
  `phrasebook add` can no longer fail on a library that has never held the
  document, because there is no document.
- **Angle images are nodes** in a `config/` folder the library is created with,
  populated through the API by `studio config sync`. Their source of truth stays
  the repo, and the library holds a copy because a model may only be handed a
  presigned URL of a stored object.

Both have node ids, `store.shared_read` / `shared_presign` are deleted, and
`?key=` is gone — `GET /api/asset` takes `?node=` and nothing else. **One
addressing scheme, no exceptions.**

The angle images were pushed straight into the bucket as `config/angle/…` for as long
as nothing owned them, and those nodeless objects outlived the change. They were
deleted in August 2026 once `config sync` had written the node-backed copies. It
was a targeted removal — `catalog gc` allowlisted the prefixes it would collect
and `config/` was never one of them — and it is the last thing that command was
used for before it was deleted.

---

## API

Every route is library-scoped by `X-Studio-Library` exactly as today, and every
entity response is membership-checked against the entity's own `lib`. **Every
route takes an id.** There was one other address, `slug:<slug>`, accepted on the
two read routes because a person types a name on a command line; it went with
slugs, because two entities may share a name and resolving one would mean
picking between them.

**Every whole-collection replace is `PATCH`, not `PUT`.** Six routes here
replace rather than merge — the profile, the reference index, the default set, a
project's character links, a scene's shots, a movie's scenes — and PUT is the
verb for that. The service registers none: a verb has to exist in the CORS list,
the MOCK integration response and two gateway responses at once, and one
omission is a browser failure carrying no status at all
(`backend/studio_core/app_factory.py`). Replace is told from merge by the body's
key instead — `{profile}` against `{patch}`.

This table spelled all six as `PUT` while the service answered `PATCH`, and both
clients believed the table: every one of those writes failed, the SPA's in the
preflight. Adopting PUT is still a one-line change in two places, and this table
moves with it.

### Characters

| Route | Body / params → result |
|---|---|
| `GET /api/characters` | `?q=` → `[{id, name, hero, counts, updated}]`, name-then-id ascending so duplicates never swap between reads |
| `POST /api/characters` | `{name, profile?}` → **201** the record. Creates entity + library index row + root + four pool folders in one transaction. **No 409** — nothing here can collide |
| `GET /api/characters/<id>` | the full record, `profile` included |
| `PATCH /api/characters/<id>` | `{name?, hero?, rev}` → **409** on a stale `rev`, and on nothing else |
| `PATCH /api/characters/<id>/profile` | `{profile, rev}` → whole-bible replace, validated. The `edit` round trip |
| `PATCH /api/characters/<id>/profile` | `{patch, rev}` → merge one section |
| `DELETE /api/characters/<id>` | `?files=keep\|delete` — refuses while a project or run still links it, unless `?force=1` |
| `PATCH /api/nodes/<id>` | `{description?, tags?}` — a reference is a file node under the character carrying tags (`default` marks identity) and a description; `studio describe` is the CLI over it |
| `GET /api/characters/<id>/selection` | `?pick=&tag=&limit=` → the ordered nodes a model would be shown, with presigned URLs. **Refuses** an over-cap selection with the index in the body — the current behaviour, moved to one place |
| `GET /api/characters/<id>/textblock` | the pasteable identity paragraph |
| `GET /api/characters/<id>/runs` | `?cursor=` → runs that used this character, newest first |
| `GET /api/characters/<id>/projects` | projects that involve it |

### Projects

| Route | Body / params → result |
|---|---|
| `GET /api/projects` | `[{id, name, hero, counts, updated}]` |
| `POST /api/projects` | `{name, description?, characters?}` → **201**. Creates entity + library index row + root + five subfolders |
| `GET /api/projects/<id>` | the record |
| `PATCH /api/projects/<id>` | `{name?, description?, hero?, rev}` |
| `DELETE /api/projects/<id>` | `?files=keep\|delete`; refuses while it holds runs unless `?force=1` |
| `PATCH /api/projects/<id>/characters` | `{characters: [id, …]}` → replaces the involvement links |
| `GET /api/projects/<id>/inputs` | the working pool, name-ascending natural sort. **Position in this list is `--input N`** |
| `GET /api/projects/<id>/runs` | `?status=&model=&character=&cursor=` |
| `GET /api/projects/<id>/scenes` · `/movies` | listings |

### Runs, scenes, movies

| Route | Body / params → result |
|---|---|
| `POST /api/runs` | `{project, kind, engine, model, input, bindings, characters?, prompt?}` → **201** `{id, folder, payload}`. Creates run + project link + character links + folder + payload blobs. **Refuses a URL-shaped binding** |
| `GET /api/runs` | `?project=&character=&model=&status=&since=&cursor=` — the query that replaces `runs find` |
| `GET /api/runs/<id>` | envelope + output nodes + the scenes that bound it |
| `PATCH /api/runs/<id>` | `{status, prediction_id?, error?, cost?, completed?}` |
| `POST /api/runs/<id>/outputs` | `{name, size, content_type}` → a node under the run's `output/` and a presigned PUT |
| `POST /api/runs/<id>/response` | `{body}` → stores the provider response as a payload blob |
| `DELETE /api/runs/<id>` | `?files=keep\|delete` |
| `POST /api/scenes` | `{project, name, shots: [...]}` → **201** |
| `GET /api/scenes` · `GET /api/scenes/<id>` · `PATCH` · `DELETE` | as above |
| `PATCH /api/scenes/<id>/shots` | `{shots: [...]}` → the plan revision; merges onto rendered work rather than replacing it |
| `PATCH /api/scenes/<id>/shots/<shot_id>` | `{run?, panel?, prompt?, order?}` |
| `POST /api/scenes/<id>/output` | `{name, size, content_type}` → upload URL for the stitched take |
| `POST /api/movies` · `GET` · `PATCH` · `DELETE` · `PATCH /api/movies/<id>/scenes` | the tier above |

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
| `GET /api/nodes?parent=` · `GET /api/nodes/<id>` · `GET /api/resolve?path=` | |
| `POST /api/nodes` `{parent, name, kind, on_conflict?}` | |
| `PATCH /api/nodes/<id>` `{name}` **or** `{parent}` | both is a 400 |
| `POST /api/nodes/move` `{ids, destination}` · `POST /api/nodes/copy` `{ids, destination}` | |
| `DELETE /api/nodes` `{ids}` · `DELETE /api/nodes/<id>` | |
| `GET/PATCH /api/nodes/<id>/text` | |
| `GET /api/nodes/<id>/download-url` · `POST /api/nodes/<id>/upload-url` · `/confirm-upload` | |
| `GET /api/nodes?under=&depth=&kind=&tag=` | one listing over a subtree |
| `GET /api/nodes/<id>/owner` | which entity a node belongs to, derived from its ancestry — what the SPA shows as "in project …" |

**A node view gains `owner`**: `{kind, id, name}` or null. It still never carries
`blob_key` or `path`.

---

## CLI

The command surface stays recognisable — the same verbs, calling the API. What
changes is that nothing composes a path and nothing writes a document.

```
session     login · logout · whoami                                unchanged

generate    run · models · add-model                               --project takes an id, or a name matched client-side
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

Ids in URLs everywhere, so every link survives every rename.

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
  status, character, date — each row showing its output thumbnail, model and
  cost. A run opens to its envelope, its outputs, and its payload documents as
  raw text (still never parsed).
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

# then merge: studio-prod.yaml applies the GSI and ships the new image
studio catalog reseat --apply     # optional, later, never automatic
```

Deploying first also works and costs a **degraded window**: from the moment
`deploy-infra` re-keys `by-recent`, the reel is blank — no row carries `reel`
yet — and the entity pages are empty until `apply` runs. File browsing is
unaffected, because nodes do not change.

**`studio config sync` is not optional in prod.** The angle images have been objects
with no node since before the catalog, and `catalog_seed` deliberately recorded
none for them. Every shoot refuses until they have rows. The old objects are
left where they are; `catalog gc` was what collected them, before it too was
deleted.

**How the CLI is pointed at prod is `--profile prod`.** This paragraph recorded
it as an open question to decide before migration day; it was decided in August
2026. The migrator is one of the maintenance commands that opens AWS clients
directly rather than going through the API, so it needs the prod table and
bucket under real AWS credentials — which is what the profile supplies:

```bash
studio profile sync prod          # once, from /studio/prod/* in SSM
studio --profile prod catalog migrate --dry-run
```

**The profile decides the target; it does not narrow the credentials.** Those
are still your own IAM key, which holds `s3:DeleteObjectVersion`. Read
[studio/CLAUDE.md](../CLAUDE.md#reaching-production---profile-prod) before
running anything with `--apply`.

**Dev stacks — no migration.** A stack holds the angle images and nothing else,
so there is no character, project or run to raise a row over. What each needs is
the re-keyed GSI and the angle images as nodes:

```bash
./studio/scripts/dev-aws-setup.sh     # applies the GSI change
./studio/scripts/dev-setup.sh         # pushes the angle images through the API
```

Given there is nothing to preserve, `dev-aws-destroy.sh` and re-provision is
cheaper and has fewer states to reason about. Either way this is **per machine**:
a stack is keyed to a persistent machine id, so it cannot be done centrally, and
a stack whose id is lost keeps billing while being unreachable.

**The seed fixture** — `publish` has still never been run, so there is nothing
there to migrate.

---
