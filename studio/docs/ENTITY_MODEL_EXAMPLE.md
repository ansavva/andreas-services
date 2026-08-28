# studio — the entity model, worked through one character and one project

> **STATUS: PROPOSED.** Companion to [ENTITY_MODEL.md](ENTITY_MODEL.md), which
> holds the reasoning and the decisions. This file holds nothing but the
> concrete shapes: the rows, the wire, the commands.

Assumes the recommended answers to D1–D5: one table, entity-prefixed S3 keys,
all five entity types, migrate prod, sparse reel index.

Names in this document are the repo's fixture placeholders (`subject-a`). Hard
rule #1 permits a named dev subject now, but a data-model walkthrough is about
the shapes rather than about anyone, so the placeholders stay.

---

## The scenario

One library holds one character and one project. The project involves the
character. One run has been submitted in it and has come back: an image on
`google/nano-banana-pro`, shown three of the character's face references.

### Legend

Every id below is a `v4` UUID with a kind prefix. Abbreviated in prose, written
in full in the rows.

| Handle | Id |
|---|---|
| the library | `lib-6c2f4a91-8e3d-4b17-9f02-1a5c7d3e9b44` |
| the character | `char-9f3c1e57-2a44-4d81-b6e0-77c21f8a4d15` |
| the project | `proj-4a10b8d2-5c93-47ae-8f61-0d51e6b7c2a9` |
| the run | `run-77c2f0a8-31b5-4e62-9a07-c4d8e15b3f60` |
| library root folder | `node-0e1c8b73-6f24-4a95-b1d3-8e07c25a9f61` |
| character root folder | `node-3b9d5a1e-4c76-42f8-9b05-1de84f3c7a02` |
| `reference/` folder | `node-5f217e04-9a3b-4c61-8d72-06fb1e59c483` |
| `reference/face/` folder | `node-7c48b0f9-1e56-4d23-a807-95c3f7b2e614` |
| a face reference image | `node-9a06d3c5-7b81-4f09-92ea-4c15b8d70f3e` |
| project root folder | `node-e51b7d28-3f60-4a14-8c95-2b07e6f1a9d4` |
| `runs/` folder | `node-f0834c16-8b25-49e7-a03f-71d5c294e8b0` |
| the run's folder | `node-12cd5f83-6a09-4b71-8e24-c9f503a7b16d` |
| the run's `output/` folder | `node-24ef9a71-0b53-4c86-91d7-3a68e5f2c904` |
| the run's output image | `node-3610c8b4-5d92-4e07-83f1-6c24a9b1e7d5` |
| the run's `request.json` | `node-4832a7e0-9c61-4b58-a274-0f93d61c85ab` |

---

## 1. DynamoDB — the rows

One table, `studio-prod-catalog`. Marshalling omitted (these are shown as plain
JSON; the table stores DynamoDB's typed form).

### 1.1 The character

**The record.** `pk = CHAR#…`, `sk = META`.

```jsonc
{
  "pk": "CHAR#char-9f3c1e57-2a44-4d81-b6e0-77c21f8a4d15",
  "sk": "META",
  "lib": "lib-6c2f4a91-8e3d-4b17-9f02-1a5c7d3e9b44",
  "slug": "subject-a",
  "display_name": "Subject A",
  "schema_version": 2,
  "rev": 4,
  "created": "2026-03-02T11:04:18.442119+00:00",
  "updated": "2026-08-19T09:41:02.883740+00:00",

  "root": "node-3b9d5a1e-4c76-42f8-9b05-1de84f3c7a02",

  "hero": "node-9a06d3c5-7b81-4f09-92ea-4c15b8d70f3e",
  "default_set": [
    "node-9a06d3c5-7b81-4f09-92ea-4c15b8d70f3e",
    "node-a18f2b60-4d95-4e37-b0c8-51f76a3d2e09",
    "node-b93e07d1-8c46-4a52-97f3-2e60d1b845c7"
  ],

  "profile": {
    "identity": {
      "apparent_age": "late 30s to mid 40s",
      "build": "<one line>",
      "height_read": "<one line>",
      "signature_features": ["<cue>", "<cue>"],
      "home_turf": "<recurring setting>",
      "register": "<demeanour>",
      "speech": "<language + accent>"
    },
    "face": {
      "structure": "<…>", "skin": "<…>", "eyes": "<…>", "eyebrows": "<…>",
      "nose": "<…>", "mouth_and_jaw": "<…>", "facial_hair": "<…>",
      "hair": "<…>", "ears": "<…>"
    },
    "body": {
      "silhouette": "<…>", "arms": "<…>", "chest_and_shoulders": "<…>",
      "back": "<…>", "hands": "<…>", "neck": "<…>",
      "midsection": "<…>", "lower_body": "<…>", "body_hair": "<…>",
      "posture": "<…>"
    },
    "wardrobe": {
      "always_dressed": true,
      "tops": [{ "item": "<garment>", "colour": "<colour>", "detail": "<…>" }],
      "lower_body": "<…>", "footwear": "<…>",
      "accessories": ["<accessory>"],
      "palette": "<…>"
    },
    "voice": {
      "language": "<…>", "accent": "<…>", "accent_cues": ["<…>"],
      "manner": "<…>", "delivery": "<…>"
    },
    "rendering": {
      "default_style": "Realistic",
      "optional_styles": [],
      "framing": "<…>", "backgrounds": "<…>"
    },
    "consistency": {
      "must": ["<…>"],
      "never": ["<…>"],
      "drift_modes": [{ "failure": "<…>", "fix": "<…>" }]
    },
    "text_identity_block": "<50-70 words, one paragraph>"
  }
}
```

Everything that was `profile.yaml` is here except two things that were
promoted to real fields (`name` → `slug`, `display_name`) and two
that became rows (`references:`, `default_set:` — the latter stays on the record
as an ordered list of node ids because it is small, ordered and read on every
generation).

**The slug claim.** `pk = LIB#…`, `sk = CHARSLUG#<slug>`. This is what makes a
slug unique in a library and what `GET /api/characters` queries.

```jsonc
{
  "pk": "LIB#lib-6c2f4a91-8e3d-4b17-9f02-1a5c7d3e9b44",
  "sk": "CHARSLUG#subject-a",
  "entity": "char-9f3c1e57-2a44-4d81-b6e0-77c21f8a4d15",
  "created": "2026-03-02T11:04:18.442119+00:00"
}
```

A pointer, not a projection — deliberately. Putting `display_name` here would
put a mutable copy on a second item that every rename has to keep in step, which
is the trap `GET /api/nodes` already avoids by pairing a query with a
`BatchGetItem`.

**A reference entry, one row per reference image.** `pk = CHAR#…`,
`sk = REF#<node_id>`.

```jsonc
{
  "pk": "CHAR#char-9f3c1e57-2a44-4d81-b6e0-77c21f8a4d15",
  "sk": "REF#node-9a06d3c5-7b81-4f09-92ea-4c15b8d70f3e",
  "lib": "lib-6c2f4a91-8e3d-4b17-9f02-1a5c7d3e9b44",
  "group": "face",
  "order": 1000,
  "description": "Three-quarter left, neutral expression, flat daylight.",
  "tags": ["face", "neutral", "daylight"],
  "created": "2026-03-02T14:22:51.019334+00:00"
}
```

`order` is gapped by 1000, so inserting between two entries is one write and a
reorder never touches its neighbours. The file it describes can be called
anything and can be renamed freely — the row names its **node id**.

Query `pk = CHAR#… AND begins_with(sk, "REF#")` is the whole reference index.

### 1.2 The project

**The record.**

```jsonc
{
  "pk": "PROJ#proj-4a10b8d2-5c93-47ae-8f61-0d51e6b7c2a9",
  "sk": "META",
  "lib": "lib-6c2f4a91-8e3d-4b17-9f02-1a5c7d3e9b44",
  "slug": "rooftop-teaser",
  "title": "Rooftop teaser",
  "description": "Short vertical cut for the launch post.",
  "rev": 2,
  "created": "2026-07-11T08:15:02.771044+00:00",
  "updated": "2026-08-19T09:41:03.104882+00:00",

  "root": "node-e51b7d28-3f60-4a14-8c95-2b07e6f1a9d4",

  "hero": "node-3610c8b4-5d92-4e07-83f1-6c24a9b1e7d5",
  "counts": { "runs": 1, "scenes": 0, "movies": 0 }
}
```

**The slug claim.**

```jsonc
{
  "pk": "LIB#lib-6c2f4a91-8e3d-4b17-9f02-1a5c7d3e9b44",
  "sk": "PROJSLUG#rooftop-teaser",
  "entity": "proj-4a10b8d2-5c93-47ae-8f61-0d51e6b7c2a9",
  "created": "2026-07-11T08:15:02.771044+00:00"
}
```

**The involvement link.** `pk = PROJ#…`, `sk = CHAR#…`.

```jsonc
{
  "pk": "PROJ#proj-4a10b8d2-5c93-47ae-8f61-0d51e6b7c2a9",
  "sk": "CHAR#char-9f3c1e57-2a44-4d81-b6e0-77c21f8a4d15",
  "lib": "lib-6c2f4a91-8e3d-4b17-9f02-1a5c7d3e9b44",
  "created": "2026-07-11T08:15:02.771044+00:00"
}
```

Read forwards (`pk = PROJ#…, begins_with(sk, "CHAR#")`) it is "who is in this
project". Read backwards on the existing `by-sk` index
(`sk = CHAR#…, begins_with(pk, "PROJ#")`) it is "which projects involve this
character" — a question that has no answer today at any price.

### 1.3 The run

**The envelope.**

```jsonc
{
  "pk": "RUN#run-77c2f0a8-31b5-4e62-9a07-c4d8e15b3f60",
  "sk": "META",
  "lib": "lib-6c2f4a91-8e3d-4b17-9f02-1a5c7d3e9b44",
  "project": "proj-4a10b8d2-5c93-47ae-8f61-0d51e6b7c2a9",
  "slug": "rooftop-portrait",
  "status": "succeeded",
  "kind": "image",
  "engine": "nano-banana-pro",
  "model": "google/nano-banana-pro",
  "prediction_id": "s7k2m9x4qwe1",

  "created":   "2026-08-19T09:40:12.664201+00:00",
  "submitted": "2026-08-19T09:40:13.902517+00:00",
  "completed": "2026-08-19T09:41:02.883740+00:00",

  "bindings": {
    "image_input": [
      "node-9a06d3c5-7b81-4f09-92ea-4c15b8d70f3e",
      "node-a18f2b60-4d95-4e37-b0c8-51f76a3d2e09",
      "node-b93e07d1-8c46-4a52-97f3-2e60d1b845c7"
    ]
  },
  "characters": ["char-9f3c1e57-2a44-4d81-b6e0-77c21f8a4d15"],

  "folder":  "node-12cd5f83-6a09-4b71-8e24-c9f503a7b16d",
  "outputs": ["node-3610c8b4-5d92-4e07-83f1-6c24a9b1e7d5"],
  "lineage": { "from_run": null, "from_output": null },
  "cost": { "currency": "USD", "amount": 0.032 },
  "error": null,

  "payload": {
    "request":  "node-4832a7e0-9c61-4b58-a274-0f93d61c85ab",
    "response": "node-5943b8f1-0d72-4c69-b385-1a04e72d96bc",
    "prompt":   null
  }
}
```

`bindings` are **node ids**. A URL-shaped binding is refused by the API, which
is where hard rule #3 now lives — it used to be enforced in `runs.py`, which
only the CLI goes through. `payload` names three nodes whose bytes studio stores
and never decodes.

**The listing row**, so a project's runs are a range query rather than a walk.

```jsonc
{
  "pk": "PROJ#proj-4a10b8d2-5c93-47ae-8f61-0d51e6b7c2a9",
  "sk": "RUN#2026-08-19T09:40:12.664201+00:00#run-77c2f0a8-31b5-4e62-9a07-c4d8e15b3f60",
  "lib": "lib-6c2f4a91-8e3d-4b17-9f02-1a5c7d3e9b44",
  "status": "succeeded",
  "model": "google/nano-banana-pro",
  "kind": "image",
  "thumb": "node-3610c8b4-5d92-4e07-83f1-6c24a9b1e7d5"
}
```

This one **is** a small projection, and that is a deliberate exception to the
rule the slug claims follow: a run is immutable once it completes, so there is
nothing to keep in step, and the runs list is the screen that would otherwise
need a `BatchGetItem` over hundreds of envelopes to draw a grid.

**The usage link**, which is what `runs find --character` becomes.

```jsonc
{
  "pk": "RUN#run-77c2f0a8-31b5-4e62-9a07-c4d8e15b3f60",
  "sk": "CHAR#char-9f3c1e57-2a44-4d81-b6e0-77c21f8a4d15",
  "lib": "lib-6c2f4a91-8e3d-4b17-9f02-1a5c7d3e9b44",
  "created": "2026-08-19T09:40:12.664201+00:00"
}
```

### 1.4 The nodes underneath

Unchanged in shape from today. Two items per node, as ever.

**The character's root folder** — a folder node like any other. Nothing about it
says "character"; the character record names it.

```jsonc
// by id
{
  "pk": "NODE#node-3b9d5a1e-4c76-42f8-9b05-1de84f3c7a02",
  "sk": "META",
  "node_id": "node-3b9d5a1e-4c76-42f8-9b05-1de84f3c7a02",
  "parent_id": "node-0e1c8b73-6f24-4a95-b1d3-8e07c25a9f61",
  "lib": "lib-6c2f4a91-8e3d-4b17-9f02-1a5c7d3e9b44",
  "name": "subject-a",
  "kind": "folder",
  "entity": "char-9f3c1e57-2a44-4d81-b6e0-77c21f8a4d15",
  "path": "/node-0e1c8b73-6f24-4a95-b1d3-8e07c25a9f61/",
  "created_at": "2026-03-02T11:04:18.442119+00:00",
  "updated_at": "2026-03-02T11:04:18.442119+00:00"
}

// by parent — what makes it listable and its name unique
{
  "pk": "NODE#node-0e1c8b73-6f24-4a95-b1d3-8e07c25a9f61",
  "sk": "NAME#subject-a",
  "node_id": "node-3b9d5a1e-4c76-42f8-9b05-1de84f3c7a02",
  "lib": "lib-6c2f4a91-8e3d-4b17-9f02-1a5c7d3e9b44",
  "kind": "folder",
  "path": "/node-0e1c8b73-6f24-4a95-b1d3-8e07c25a9f61/",
  "created_at": "2026-03-02T11:04:18.442119+00:00"
}
```

> The folder is *named* `subject-a` because that is convenient to browse. It is
> not addressed by it. Rename the character and this folder's `name` changes in
> the same transaction; nothing else in the library moves or is rewritten.
>
> `entity` is the reverse pointer — one attribute, written once, never changed.
> It is what lets a listing draw a character card instead of a folder icon, and
> what `GET /api/nodes/<id>/owner` walks up to. The forward pointer is `root` on
> the character record. One field in each direction, and no map of folder names
> in either.

**A face reference image** — the file the `REF#` row describes.

```jsonc
{
  "pk": "NODE#node-9a06d3c5-7b81-4f09-92ea-4c15b8d70f3e",
  "sk": "META",
  "node_id": "node-9a06d3c5-7b81-4f09-92ea-4c15b8d70f3e",
  "parent_id": "node-7c48b0f9-1e56-4d23-a807-95c3f7b2e614",
  "lib": "lib-6c2f4a91-8e3d-4b17-9f02-1a5c7d3e9b44",
  "name": "three-quarter-left.png",
  "kind": "file",
  "blob_key": "characters/char-9f3c1e57-2a44-4d81-b6e0-77c21f8a4d15/node-9a06d3c5-7b81-4f09-92ea-4c15b8d70f3e.png",
  "size": 2214809,
  "content_type": "image/png",
  "reel": "lib-6c2f4a91-8e3d-4b17-9f02-1a5c7d3e9b44",
  "path": "/node-0e1c8b73-…/node-3b9d5a1e-…/node-5f217e04-…/node-7c48b0f9-…/",
  "created_at": "2026-03-02T14:22:50.884210+00:00",
  "updated_at": "2026-03-02T14:22:51.019334+00:00"
}
```

Three things to notice:

- **`name` carries no slug, no group and no number.** `<slug>_face_1.png` is
  dead. Group and order are on the `REF#` row.
- **`blob_key` carries the character's id and the node's id, and nothing else.**
  A bucket listing leaks no names.
- **`reel`** is the sparse-index key from D5 — written only on file nodes whose
  content type is an image or a video, so folders and entity rows stay out of
  the reel's enumeration.

**The run's output image**, showing the project-owned key:

```jsonc
{
  "pk": "NODE#node-3610c8b4-5d92-4e07-83f1-6c24a9b1e7d5",
  "sk": "META",
  "node_id": "node-3610c8b4-5d92-4e07-83f1-6c24a9b1e7d5",
  "parent_id": "node-24ef9a71-0b53-4c86-91d7-3a68e5f2c904",
  "lib": "lib-6c2f4a91-8e3d-4b17-9f02-1a5c7d3e9b44",
  "name": "output-1.png",
  "kind": "file",
  "blob_key": "projects/proj-4a10b8d2-5c93-47ae-8f61-0d51e6b7c2a9/node-3610c8b4-5d92-4e07-83f1-6c24a9b1e7d5.png",
  "size": 3980112,
  "content_type": "image/png",
  "reel": "lib-6c2f4a91-8e3d-4b17-9f02-1a5c7d3e9b44",
  "path": "/node-0e1c8b73-…/node-e51b7d28-…/node-f0834c16-…/node-12cd5f83-…/node-24ef9a71-…/",
  "created_at": "2026-08-19T09:41:01.220760+00:00",
  "updated_at": "2026-08-19T09:41:02.410558+00:00"
}
```

### 1.5 The whole library, as rows

```
LIB#lib-6c2f…          META                                    the library
LIB#lib-6c2f…          CHARSLUG#subject-a                      slug claim
LIB#lib-6c2f…          PROJSLUG#rooftop-teaser                 slug claim
LIB#lib-6c2f…          TERM#google/nano-banana-pro#<avoid>     phrasebook
USER#<cognito sub>     LIB#lib-6c2f…                           membership

CHAR#char-9f3c…        META                                    the character
CHAR#char-9f3c…        REF#node-9a06…                          a reference entry
CHAR#char-9f3c…        REF#node-a18f…                          …
PROJ#proj-4a10…        META                                    the project
PROJ#proj-4a10…        CHAR#char-9f3c…                         involvement
PROJ#proj-4a10…        RUN#2026-08-19T09:40:12.664201+00:00#run-77c2…
RUN#run-77c2…          META                                    the envelope
RUN#run-77c2…          CHAR#char-9f3c…                         usage

NODE#node-0e1c…        META                                    library root
NODE#node-0e1c…        NAME#subject-a                          → character root
NODE#node-0e1c…        NAME#rooftop-teaser                     → project root
NODE#node-3b9d…        META                                    character root
NODE#node-3b9d…        NAME#reference                          …and so on
…
```

### 1.6 Queries, and what each costs

| Question | Query | Cost |
|---|---|---|
| Every character in the library | `pk = LIB#…, begins_with(sk, "CHARSLUG#")` + `BatchGetItem` | 1 query + ⌈n/100⌉ reads |
| One character by slug | `GetItem(LIB#…, CHARSLUG#<slug>)` then `GetItem(CHAR#…, META)` | 2 reads |
| Its reference index | `pk = CHAR#…, begins_with(sk, "REF#")` | 1 query |
| Its `reference/face/` folder listing | `pk = NODE#<face folder>` | 1 query |
| Every project involving it | `by-sk`: `sk = CHAR#…, begins_with(pk, "PROJ#")` | 1 query |
| Every run that used it | `by-sk`: `sk = CHAR#…, begins_with(pk, "RUN#")` | 1 query |
| A project's runs, newest first, paged | `pk = PROJ#…, begins_with(sk, "RUN#"), ScanIndexForward=false` | 1 query, real pagination |
| The reel | `by-recent` on the sparse `reel` key | 1 query |
| Everything under a subtree | `by-path`: `lib = …, begins_with(path, …)` | 1 query |

Today, three of those are a walk over every project's every run folder, reading
three JSON documents each.

---

## 2. The API

Every call carries `Authorization: Bearer <Cognito ID token>` and
`X-Studio-Library: lib-6c2f…`. Both omitted below for brevity. Errors are the
existing shape: `{"error": "...", "message": "..."}`.

### 2.1 Create the character

```http
POST /api/characters
Content-Type: application/json

{
  "slug": "subject-a",
  "display_name": "Subject A"
}
```

```http
201 Created
Location: /api/characters/char-9f3c1e57-2a44-4d81-b6e0-77c21f8a4d15

{
  "id": "char-9f3c1e57-2a44-4d81-b6e0-77c21f8a4d15",
  "lib": "lib-6c2f4a91-8e3d-4b17-9f02-1a5c7d3e9b44",
  "slug": "subject-a",
  "display_name": "Subject A",
  "rev": 1,
  "created": "2026-03-02T11:04:18.442119+00:00",
  "updated": "2026-03-02T11:04:18.442119+00:00",
  "root": "node-3b9d5a1e-…",
  "hero": null,
  "default_set": [],
  "profile": { …the template, empty… }
}
```

Twelve items in one `TransactWriteItems`: the record, the slug claim, and two
items each for the root folder and the four starting pool folders. Either all of
it exists or none of it does.

**The four pools are a starting layout, not a schema.** They are created because
an empty character is unhelpful; nothing afterwards requires them. Rename
`reference/`, delete `archive/`, add `wardrobe-refs/` — all ordinary file
operations, and none of them breaks anything, because an image is a reference
when a `REF#` row says so and not because of the folder it sits in. The record
holds one node id, `root`, and no map of blessed folder names. See
[the layout section](ENTITY_MODEL.md#the-folder-layout-is-convention-not-schema).

```http
409 Conflict
{ "error": "conflict", "message": "a character called 'subject-a' already exists" }
```

### 2.2 List and read

```http
GET /api/characters
```
```json
[
  {
    "id": "char-9f3c1e57-…",
    "slug": "subject-a",
    "display_name": "Subject A",
    "hero": { "node": "node-9a06d3c5-…", "url": "https://…presigned…" },
    "counts": { "references": 41, "files": 62 },
    "updated": "2026-08-19T09:41:02.883740+00:00"
  }
]
```

```http
GET /api/characters/slug:subject-a
```

Returns the full record from §1.1, with `profile` inline. `slug:` addressing
exists for the CLI, where a person types a name; the SPA always holds an id.

### 2.3 Rename

```http
PATCH /api/characters/char-9f3c1e57-…
{ "slug": "subject-b", "rev": 4 }
```
```json
{ "id": "char-9f3c1e57-…", "slug": "subject-b", "rev": 5, "updated": "…" }
```

Four writes in one transaction: delete the old slug claim, put the new one under
`attribute_not_exists(pk)`, update the record, rename the root folder node. **No
object is copied. No record anywhere is rewritten. Every node keeps its id.**

Today this is a `PATCH` per slugged basename in four pools, plus a rewrite pass
over every run document that cited the old path.

```http
409 Conflict
{ "error": "conflict", "message": "the character was changed by someone else; re-read and retry (rev 4 → 5)" }
```

### 2.4 Attach and describe references

```http
POST /api/characters/char-9f3c1e57-…/references
{
  "node": "node-9a06d3c5-…",
  "group": "face",
  "description": "Three-quarter left, neutral expression, flat daylight.",
  "tags": ["face", "neutral", "daylight"],
  "after": "node-a18f2b60-…"
}
```
```json
{
  "node": "node-9a06d3c5-…", "group": "face", "order": 1500,
  "description": "Three-quarter left, neutral expression, flat daylight.",
  "tags": ["face", "neutral", "daylight"],
  "file": { "name": "three-quarter-left.png", "size": 2214809,
            "content_type": "image/png",
            "url": "https://…presigned…" }
}
```

`after` places the entry between two existing ones by picking the midpoint of
their `order` values. One write, no neighbours touched.

Bulk describe — one transaction, which is what `describe-refs` needs:

```http
PATCH /api/characters/char-9f3c1e57-…/references
{
  "entries": [
    { "node": "node-9a06d3c5-…", "group": "face", "description": "…" },
    { "node": "node-a18f2b60-…", "group": "face", "description": "…" },
    { "node": "node-b93e07d1-…", "group": "body", "description": "…" }
  ]
}
```

Read them back, grouped and ordered:

```http
GET /api/characters/char-9f3c1e57-…/references?group=face
```
```json
{
  "groups": {
    "face": [
      { "node": "node-a18f2b60-…", "order": 1000, "description": "…",
        "tags": ["face"], "default": true,
        "file": { "name": "front-neutral.png", "url": "https://…" } },
      { "node": "node-9a06d3c5-…", "order": 1500, "description": "…",
        "tags": ["face","neutral","daylight"], "default": true,
        "file": { "name": "three-quarter-left.png", "url": "https://…" } }
    ]
  },
  "counts": { "face": 18, "body": 14, "wardrobe": 6, "frame": 3 }
}
```

### 2.5 Resolve what a model will actually be shown

The one route that both halves of studio must agree on, which is why it is a
route rather than a function in each.

```http
GET /api/characters/char-9f3c1e57-…/selection?tag=face&limit=7
```
```json
{
  "selection": [
    { "slot": 1, "node": "node-a18f2b60-…", "group": "face",
      "description": "…", "url": "https://…presigned…" },
    { "slot": 2, "node": "node-9a06d3c5-…", "group": "face",
      "description": "…", "url": "https://…presigned…" },
    { "slot": 3, "node": "node-b93e07d1-…", "group": "face",
      "description": "…", "url": "https://…presigned…" }
  ],
  "cap": 7,
  "source": "tag"
}
```

Over-cap is refused with the index in the body, not truncated — the current
behaviour, moved somewhere both callers share:

```http
409 Conflict
{
  "error": "over_cap",
  "message": "18 references match tag 'face'; nano-banana-pro accepts 14",
  "index": [ { "node": "node-…", "group": "face", "description": "…" }, … ]
}
```

### 2.6 Create the project and link the character

```http
POST /api/projects
{ "slug": "rooftop-teaser", "title": "Rooftop teaser",
  "description": "Short vertical cut for the launch post.",
  "characters": ["char-9f3c1e57-…"] }
```
```json
{
  "id": "proj-4a10b8d2-…", "slug": "rooftop-teaser",
  "title": "Rooftop teaser", "rev": 1,
  "root": "node-e51b7d28-…",
  "characters": [ { "id": "char-9f3c1e57-…", "slug": "subject-a",
                    "display_name": "Subject A" } ],
  "counts": { "runs": 0, "scenes": 0, "movies": 0 }
}
```

### 2.7 Record a run

Before the submission, so a prediction that times out still leaves a record —
the reason `request.json` and `result.json` were two writes, preserved as two
calls.

```http
POST /api/runs
{
  "project": "proj-4a10b8d2-…",
  "slug": "rooftop-portrait",
  "kind": "image",
  "engine": "nano-banana-pro",
  "model": "google/nano-banana-pro",
  "bindings": { "image_input": ["node-9a06d3c5-…", "node-a18f2b60-…",
                                "node-b93e07d1-…"] },
  "characters": ["char-9f3c1e57-…"],
  "input": { "prompt": "…", "aspect_ratio": "9:16", "resolution": "4k" }
}
```
```json
{
  "id": "run-77c2f0a8-…",
  "status": "pending",
  "folder": "node-12cd5f83-…",
  "payload": { "request": "node-4832a7e0-…", "response": null, "prompt": null },
  "created": "2026-08-19T09:40:12.664201+00:00"
}
```

The API writes the run folder, the `output/` folder, the envelope, the project
listing row, the character usage rows, and `request.json` as a payload blob —
one transaction plus one object write.

A URL where a node id belongs is refused here, which is hard rule #3 enforced
for both callers rather than only for the CLI:

```http
400 Bad Request
{ "error": "invalid_binding",
  "message": "bindings.image_input[0] is a URL; bindings name nodes. S3 is the only origin." }
```

Then the outputs, one presigned PUT each:

```http
POST /api/runs/run-77c2f0a8-…/outputs
{ "name": "output-1.png", "size": 3980112, "content_type": "image/png" }
```
```json
{
  "node": "node-3610c8b4-…",
  "url": "https://studio-prod-media-us-east-1.s3.amazonaws.com/projects/proj-4a10b8d2-…/node-3610c8b4-….png?X-Amz-…",
  "headers": { "Content-Type": "image/png", "Content-Length": "3980112" }
}
```

And the completion:

```http
PATCH /api/runs/run-77c2f0a8-…
{ "status": "succeeded", "prediction_id": "s7k2m9x4qwe1",
  "completed": "2026-08-19T09:41:02.883740+00:00",
  "cost": { "currency": "USD", "amount": 0.032 } }
```

### 2.8 Query runs

The route that replaces a walk over every project's every run folder:

```http
GET /api/runs?character=char-9f3c1e57-…&status=succeeded&model=google/nano-banana-pro&limit=20
```
```json
{
  "runs": [
    { "id": "run-77c2f0a8-…", "project": "proj-4a10b8d2-…",
      "slug": "rooftop-portrait", "status": "succeeded", "kind": "image",
      "model": "google/nano-banana-pro",
      "created": "2026-08-19T09:40:12.664201+00:00",
      "cost": { "currency": "USD", "amount": 0.032 },
      "thumb": { "node": "node-3610c8b4-…", "url": "https://…presigned…" } }
  ],
  "cursor": null
}
```

```http
GET /api/runs/run-77c2f0a8-…
```

Returns the envelope of §1.3, with `outputs` and `bindings` expanded to node
records and presigned URLs, and `payload` as three node ids the caller may fetch
as text — still never decoded by studio.

### 2.9 The file layer, unchanged in behaviour

```http
GET /api/nodes?parent=node-7c48b0f9-…
```
```json
[
  { "id": "node-9a06d3c5-…", "name": "three-quarter-left.png", "kind": "file",
    "size": 2214809, "content_type": "image/png",
    "created_at": "…", "updated_at": "…",
    "owner": { "kind": "character", "id": "char-9f3c1e57-…", "slug": "subject-a" } }
]
```

`owner` is the one new field, derived from the node's ancestry rather than
stored — it is what the SPA shows as "in subject-a" and what stamps the blob
prefix on upload. Still no `blob_key`, still no `path`.

Rename, move, copy, upload and delete are the existing routes with the name-path
variants dropped:

```http
PATCH /api/nodes/node-9a06d3c5-…          { "name": "three-quarter-left-v2.png" }
POST  /api/nodes/move                      { "ids": [...], "destination": "node-…" }
POST  /api/nodes/copy                      { "ids": [...], "destination": "node-…" }
DELETE /api/nodes                          { "ids": [...] }
POST  /api/nodes/node-…/upload-url         { "size": …, "content_type": "…" }
```

Renaming that file changes one row. Its `REF#` description, the run that used it
as a binding, and the `default_set` that names it are all untouched, because all
three name `node-9a06d3c5-…`.

---

## 3. The CLI

Same flow as §2, in the order a person would actually do it. Every command is
one or two API calls and nothing else; there is no AWS credential anywhere in
this package.

### 3.1 The character

```bash
$ studio character create subject-a --display-name "Subject A"
created character subject-a  (char-9f3c1e57-…)
  reference/  corpus/  seed/  archive/
# POST /api/characters

$ studio character edit subject-a
# GET /api/characters/slug:subject-a → local/characters/subject-a.yaml → $EDITOR
wrote local/characters/subject-a.yaml — edit, then: studio character set-profile subject-a

$ studio character set-profile subject-a
profile updated (rev 1 → 2)
# PATCH /api/characters/<id>/profile  {profile, rev}

$ studio character list
subject-a   Subject A    refs 41   files 62   updated 2026-08-19

$ studio character show subject-a
subject-a  (char-9f3c1e57-…)  rev 4
  display   Subject A
  refs      face 18 · body 14 · wardrobe 6 · frame 3      default set: 3
  root      node-3b9d5a1e-…   reference/ corpus/ seed/ archive/ my-notes/
```

**References.** Adding one is two steps and always has been: the bytes arrive,
then a person decides it is identity (hard rule #2b).

```bash
$ studio character add-refs subject-a --to face --from-run rooftop-teaser/latest
copied 1 file into subject-a/reference/face/
  node-9a06d3c5-…  three-quarter-left.png
attached as reference (group face, order 1500)
# POST /api/nodes/copy  →  POST /api/characters/<id>/references

$ studio character refs subject-a --group face
  order  node             name                      description
   1000  node-a18f2b60-…  front-neutral.png         Front, neutral, flat daylight.
   1500  node-9a06d3c5-…  three-quarter-left.png    Three-quarter left, neutral…
# GET /api/characters/<id>/references?group=face

$ studio character set-ref-desc subject-a node-9a06d3c5-… "Three-quarter left, neutral expression, flat daylight."
described 1 reference
# PATCH /api/characters/<id>/references/<node>

$ studio character describe-refs subject-a --from descriptions.json
described 12 references in one write
# PATCH /api/characters/<id>/references

$ studio character order subject-a --group face node-9a06d3c5-… --after node-a18f2b60-…
reordered
# PATCH /api/characters/<id>/references/<node>  {after}

$ studio character regroup subject-a node-b93e07d1-… --to body
moved to group body — no object was written
# PATCH /api/characters/<id>/references/<node>  {group}

$ studio character default-set subject-a node-a18f2b60-… node-9a06d3c5-… node-b93e07d1-…
default set: 3 references
# PATCH /api/characters/<id>/default-set

$ studio character selection subject-a --tag face --limit 7
slot 1  node-a18f2b60-…  face  Front, neutral, flat daylight.
slot 2  node-9a06d3c5-…  face  Three-quarter left, neutral expression…
# GET /api/characters/<id>/selection
```

**Rename**, which is the command that changes character most:

```bash
$ studio character rename subject-a subject-b
renamed subject-a → subject-b
  0 objects copied · 0 records rewritten · 41 references untouched
# PATCH /api/characters/<id>  {slug, rev}
```

### 3.2 The project

```bash
$ studio projects new rooftop-teaser --title "Rooftop teaser" --character subject-a
created project rooftop-teaser  (proj-4a10b8d2-…)
  runs/  scenes/  movies/  chains/  input/
# POST /api/projects

$ studio projects list
rooftop-teaser   Rooftop teaser   characters: subject-a   runs 1   scenes 0   movies 0

$ studio projects show rooftop-teaser
rooftop-teaser  (proj-4a10b8d2-…)  rev 2
  title       Rooftop teaser
  characters  subject-a
  runs 1 · scenes 0 · movies 0
  input pool  4 images

$ studio projects link rooftop-teaser subject-b
# PATCH /api/projects/<id>/characters

$ studio projects rename rooftop-teaser launch-teaser
renamed — 0 objects copied
# PATCH /api/projects/<id>

$ studio projects add-inputs rooftop-teaser ./plate.png
added 1 → position 5
# POST /api/nodes  →  upload-url  →  confirm-upload

$ studio projects inputs rooftop-teaser
  1  node-…  street-plate.png
  2  node-…  rooftop-plate.png
# GET /api/projects/<id>/inputs   (position is what --input N means)
```

### 3.3 Generating, and reading back

```bash
$ studio run --project rooftop-teaser --model nano-banana-pro \
             --character subject-a --pick-tag face \
             --prompt "…" --aspect 9:16 --resolution 4k --dry-run
# GET /api/characters/slug:subject-a → /selection?tag=face
# renders PROMPT and INPUT for approval. Nothing is submitted. (hard rule #2)

$ studio run --project rooftop-teaser --model nano-banana-pro \
             --character subject-a --pick-tag face \
             --prompt "…" --aspect 9:16 --resolution 4k
run-77c2f0a8-…  submitted   s7k2m9x4qwe1
run-77c2f0a8-…  succeeded   1 output   $0.032
  node-3610c8b4-…  output-1.png
# POST /api/runs → provider → POST /api/runs/<id>/outputs → PATCH /api/runs/<id>

$ studio runs list rooftop-teaser --model nano-banana-pro --status succeeded
2026-08-19 09:40  run-77c2f0a8-…  rooftop-portrait  image  succeeded  $0.032
# GET /api/runs?project=…&model=…&status=…      (one query)

$ studio runs find --character subject-a
rooftop-teaser  run-77c2f0a8-…  2026-08-19  image  succeeded
# GET /api/runs?character=…                      (one query; today, a full walk)

$ studio runs show rooftop-teaser/latest
run-77c2f0a8-…  succeeded
  project     rooftop-teaser
  model       google/nano-banana-pro     prediction s7k2m9x4qwe1
  characters  subject-a
  bindings    image_input → 3 nodes
  outputs     node-3610c8b4-…  output-1.png  3.8 MB
  cost        $0.032

$ studio runs show rooftop-teaser/latest --payload
# prints request.json and response.json verbatim; studio does not decode either

$ studio runs outputs rooftop-teaser/latest --presign
https://studio-prod-media-us-east-1.s3.amazonaws.com/projects/proj-4a10…/node-3610…png?X-Amz-…
```

### 3.4 Files, which work as they always did

```bash
$ studio upload ./plate.png --to subject-a/corpus
uploaded node-7f2a91c3-…  plate.png
# POST /api/nodes → upload-url → confirm-upload

$ studio download subject-a/reference/face --to ./out
$ studio presign subject-a/reference/face/three-quarter-left.png
```

`subject-a/reference/face/…` is still what a person types. It is resolved
through `GET /api/resolve?path=` against the character's root folder — an
**address**, not a key. The S3 key behind that last one is
`characters/char-9f3c1e57-…/node-9a06d3c5-….png`, and nothing but
`services/catalog.py` ever sees it.

### 3.5 Commands that stop existing

```bash
$ studio curate renumber …     # gone — order is a row attribute
$ studio rewrite check         # gone — records name node ids; nothing can dangle
$ studio character sync-refs   # gone — the index cannot drift from the folder
```
