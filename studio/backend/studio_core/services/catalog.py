"""The catalog: libraries, nodes, entities, and every write that changes one.

**This is the only module that knows the table's item shapes.** Everything above
it — routes, and the services that will grow beside them — deals in node records
and library ids, never in a `pk`, an `sk` or a `NAME#` prefix. That boundary is
the point of the module rather than tidiness: the two-item-per-node layout below
is a consequence of wanting list-by-parent *and* unique-name-per-folder out of
one table, and it must not leak into a route handler that would then have to be
rewritten if the layout ever changed.

## What is in the table

```
Library     lib-<uuid>     the sharing unit; has members
 ├ Node     node-<uuid>    a folder or a file, with a parent pointer
 ├ Character char-<uuid>   who a subject is
 ├ Project  proj-<uuid>    a unit of production
 ├ Run      run-<uuid>     one submission to a model
 ├ Scene    scene-<uuid>   shots stitched into one continuous take
 └ Movie    movie-<uuid>   scenes cut into one piece
```

One node type. A folder is a node with no blob; a file is a node with one.

| Item | `pk` | `sk` | Why |
|---|---|---|---|
| Library | `LIB#<lib_id>` | `META` | |
| Membership | `USER#<sub>` | `LIB#<lib_id>` | |
| Node — by parent | `NODE#<parent_id>` | `NAME#<name>` | list-by-parent, unique names |
| Node — by id | `NODE#<node_id>` | `META` | the record |
| Character | `CHAR#<char_id>` | `META` | the record |
| Character index | `LIB#<lib>` | `CHAR#<char_id>` | the listing |
| Project | `PROJ#<proj_id>` | `META` | the record |
| Project index | `LIB#<lib>` | `PROJ#<proj_id>` | the listing |
| Project ↔ character | `PROJ#<proj_id>` | `CHAR#<char_id>` | involvement; reverse-queryable |
| Run | `RUN#<run_id>` | `META` | the envelope |
| Run in project | `PROJ#<proj_id>` | `RUN#<created>#<run_id>` | newest first, paginated |
| Run ↔ character | `RUN#<run_id>` | `CHAR#<char_id>` | which characters a run used |
| Scene / Movie | `SCENE#…` / `MOVIE#…` | `META` | |
| Scene / Movie in project | `PROJ#<proj_id>` | `SCENE#<created>#<id>` | |
| Shot | `SCENE#<scene_id>` | `SHOT#<shot_id>` | one row per planned shot |
| Phrasebook term | `LIB#<lib>` | `TERM#<model>#<avoid>` | the wording lists |
| Block | `LIB#<lib>` | `SPEC#BLOCK#<name>` | shared prose, cited BY NAME in a prompt |
| Template | `LIB#<lib>` | `SPEC#TEMPLATE#<template_id>` | the record |
| Sweep | `LIB#<lib>` | `SWEEP#<opened>#<id>#<n>` | blobs a delete is about to strand |

**An id is the identity; a name is a label.** Every entity has a `v4` UUID that
never changes, and the name is a mutable free-text attribute — not unique, not
claimed, and nothing resolves an entity by it. A rename is
one conditional write plus a folder rename and touches nothing else, ever — no
object is copied, no record anywhere is rewritten, and every node keeps its id.
That is the single largest simplification the entity model buys, and it is why
`domain/rewrite.py` and the whole class of stranded-path bug stop existing.

**A node is two items, so every write here is a `TransactWriteItems`.** The
by-parent item is what makes a folder listable and what makes a name unique
inside it; the by-id item is the record. There is no write that touches one
without the other, and no code path in this module that puts an item outside a
transaction — a node that exists under one key and not the other is a node that
either cannot be listed or cannot be opened.

## The three rules this module holds

* **A name collision is a condition failure, never a read.** `create_node`,
  `rename_node` and `move_node` put their `NAME#` item under
  `attribute_not_exists(pk)` and turn the cancelled transaction into
  `ConflictError` — the 409 the API already returns. Checking first and writing
  second would be a race with a window, and the whole reason the catalog is a
  database rather than a bucket is that this check can be made atomically. (In
  `services.manage`, which writes to S3, the same check *is* a read-then-write,
  because S3 offers nothing better. That is the difference worth noticing
  between the two modules.)
* **`parent_id` is authoritative; `path` is a derived index.** `path` is the
  materialised list of ancestor ids, `/node-a/node-b/`, and exists so a subtree
  can be read with one `begins_with` query instead of a walk. A move rewrites it
  across every descendant. If a move were interrupted, `path` would be stale and
  could be rebuilt from `parent_id`; nothing can rebuild `parent_id`, which is
  why it is written first — see `move_node`. **`lib` is derived in the same
  sense** — a node is in the library its parent is in.
* **`blob_key` is stamped once and never re-derived.** It is built by
  `blob_key_for` at creation, from the owner the parent already resolves to, and
  after that it is a pointer that nothing splits, rewrites or recomputes. Every
  key in prod is `<owner_kind>/<owner_id>/…`, and it stays correct forever
  precisely because the text carries no meaning to any reader. The one thing
  that reads a key is `is_api_blob`, which looks at the
  **tail** — `<node_id>.<ext>`, which cannot change — and never at the prefix,
  which drifts the moment a node moves between owners.

## The library root is an ordinary node

`root_node` on the library names a real `NODE#<id>`/`META` row, with `path`
`"/"` and **no** `parent_id`. The alternative — a root that is only an id on the
library item — means every function that needs a parent's `path` has a special
case for "the parent is the root", and `create_node` would have to read the
library to find out. A root that is a node costs one row and removes that branch
everywhere.

Its missing `parent_id` is then load-bearing: it is what makes "rename the
library root", "move it" and "delete it" refuse, since there is no `NAME#` item
to rewrite.

## What this module does not do

It never touches S3. `delete_node` returns the `blob_key` values it removed
rows for rather than deleting the objects behind them, because two nodes may
point at one key — a copy in this model copies a row, not bytes — so whether a
blob is now unreferenced is not a question a single delete can answer.
"""

import collections
import logging
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from studio_core import config
from studio_core.clients.aws import dynamodb
from studio_core.errors import ConflictError, NotFoundError, UpstreamError, ValidationError
from studio_core.services import digest, keys, storyboard
# Re-exported so every caller keeps saying `catalog.plan_digest(...)`. They live
# in `digest.py` because the pipeline's test fake loads that module rather than
# restating the hash — see its docstring.
from studio_core.services.digest import (  # noqa: F401
    plan_digest,
    submission_fingerprint,
)

logger = logging.getLogger(__name__)

KIND_FOLDER = "folder"
KIND_FILE = "file"
KINDS = frozenset({KIND_FOLDER, KIND_FILE})

# `by-path` is the subtree index: hashed on `lib`, ranged on `path`, so one
# `begins_with` reads a whole branch.
#
# **`by-recent` is hashed on `reel`, which holds the library id and is not
# `lib`.** The two carry the same string and that is exactly why the distinction
# has to be spelled out: a DynamoDB item enters a GSI only when it carries both
# of that index's key attributes, so what the attribute is *named* decides who is
# in the index. `reel` is written onto file nodes whose extension reads as an
# image or a video and onto nothing else — so folder nodes, entity records,
# membership rows and entity index rows all carry `lib`, all carry a timestamp,
# and all stay out.
#
# Sparse on purpose. Hashed on `lib`, every folder in the library would enter
# the reel's enumeration and be filtered out in memory by `browse.entries` —
# after being counted against `config.max_folder_objects`. A sparse index
# spends the cap on rows the reel can actually show.
#
# `by-sk` inverts the table so a sort key can be asked who points at it: "every
# project involving this character" is
# `sk = CHAR#<id> AND begins_with(pk, "PROJ#")`, and "every run that used it" is
# the same query one prefix over.
BY_PATH_INDEX = "by-path"
BY_RECENT_INDEX = "by-recent"
BY_SK_INDEX = "by-sk"

# The attribute `by-recent` is hashed on. Its value is the library id.
REEL_ATTRIBUTE = "reel"

# What a node has to look like to be in the reel. Classified from the *name*
# rather than from `content_type`, for `browse._file_entry`'s reason: the header
# is what an uploader claimed and the extension is what a browser will actually
# try to decode. A file created before its bytes land has no content type at all,
# and it still has to be in the reel the moment they do.
REEL_KINDS = frozenset({"image", "video"})

# The five entity kinds. Ids are `<prefix>-<uuid4>`; the prefix is for a human
# reading a log, and the one thing in this service that reads it back is
# `entity_kind` — see there for why that one exception has to exist.
ENTITY_CHARACTER = "character"
ENTITY_PROJECT = "project"
ENTITY_RUN = "run"
ENTITY_SCENE = "scene"
ENTITY_MOVIE = "movie"

# kind -> (id prefix, partition prefix). The partition prefix is also the sort
# key prefix of the listing row a project keeps for its runs, scenes and movies,
# and of the link rows that point at a character — one string per kind rather
# than three that have to agree.
ENTITY_KEYS = {
    ENTITY_CHARACTER: ("char", "CHAR#"),
    ENTITY_PROJECT: ("proj", "PROJ#"),
    ENTITY_RUN: ("run", "RUN#"),
    ENTITY_SCENE: ("scene", "SCENE#"),
    ENTITY_MOVIE: ("movie", "MOVIE#"),
}
_KIND_BY_ID_PREFIX = {prefix: kind for kind, (prefix, _) in ENTITY_KEYS.items()}

#: Which entity kinds a library lists. The sort key is the entity's own pk —
#: `CHAR#<char_id>` under `LIB#<lib>` — so the index row and the record it points
#: at are spelled the same way and `_member_sk` is `_entity_pk`.
LISTED_KINDS = (ENTITY_CHARACTER, ENTITY_PROJECT)

# The three kinds a project lists, and the folder each one's tree hangs under.
# `services.layout` owns the folder *names*; this is only the set.
PROJECT_ENTITIES = (ENTITY_RUN, ENTITY_SCENE, ENTITY_MOVIE)

# What `counts` on a project record holds, keyed by the entity kind that moves
# it. Maintained inside the transaction that creates or deletes the entity, so a
# count is never a scan and never drifts by one.
COUNT_FIELD = {ENTITY_RUN: "runs", ENTITY_SCENE: "scenes", ENTITY_MOVIE: "movies"}

# What a run's `status` may be. Studio owns this word — it is the one thing about
# a submission this service is willing to have an opinion on — while the
# provider's own response stays an undecoded blob beside it.
RUN_STATUSES = frozenset({
    "draft", "pending", "running", "succeeded", "failed",
    "cancelled", "discarded", "adopted",
})

#: A synthetic run wrapping an artifact that already existed — `studio runs
#: adopt`, which files a pre-scheme file so history is uniform. **Nothing was
#: submitted and nothing billed**, so it is the one way out of the unsubmitted
#: states that is not a submission and is not counted as one.
ADOPTED = "adopted"

#: The two that come BEFORE a submission. A run is created when it is PLANNED
#: — which is what makes a plan editable and viewable — so the existence of a
#: row does not say anything happened.
#:
#: Both are kept out of every default listing and out of the project's run
#: count for exactly that reason: a grid mixing intentions with submissions is
#: a grid nobody can read.
UNSUBMITTED_RUN_STATUSES = frozenset({"draft", "discarded"})

#: What a default listing hides. The same set, named for the other reason a
#: caller reads it.
HIDDEN_RUN_STATUSES = frozenset({"draft", "discarded"})

# The states a run does not come back from. Studio owns this word, so it owns
# which of its values are endings — the alternative is every caller writing its
# own set and one of them forgetting `cancelled`.
#
# It exists because the app polls: a client that knows which states are
# terminal can stop asking on its own.
TERMINAL_RUN_STATUSES = frozenset({"succeeded", "failed", "cancelled", "discarded"})

# The sort key of the record half of a node, of a library, and of every entity.
META = "META"

# DynamoDB's hard ceiling on one `TransactWriteItems`. A subtree rewrite is two
# items per node — the record and its by-parent item — so it moves fifty nodes
# per call.
TRANSACTION_ITEMS = 100

# DynamoDB's ceiling on one `BatchGetItem`, and how many times a *partial*
# answer is asked again before it becomes an error. The two numbers belong
# together: the batch is where `UnprocessedKeys` comes from, and a caller that
# chunked without retrying would silently return fewer nodes than it was asked
# for. See `records`.
BATCH_GET_KEYS = 100
BATCH_GET_ATTEMPTS = 4

# The first pause before re-asking for unprocessed keys, doubling each attempt.
# Small on purpose: `UnprocessedKeys` on a PAY_PER_REQUEST table means a brief
# partition throttle, and this runs inside a request a person is waiting on.
BATCH_GET_BACKOFF = 0.05

_marshal = TypeSerializer().serialize
_deserialize = TypeDeserializer().deserialize


def _decimals(value):
    """Turn every `float` on the way *in* into a `Decimal`.

    **`TypeSerializer` refuses a float outright** — DynamoDB's N is a decimal
    type and boto3 will not guess a binary-float rounding for you. A run's
    recorded cost — `{"amount": 0.032}` arriving from a JSON body — is a float
    every time.

    The conversion goes through `str` rather than `Decimal(value)` so that 0.032
    is stored as 0.032 and not as the seventeen digits its binary
    representation actually is. `_numbers` does the reverse on the way out.
    """
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _decimals(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimals(item) for item in value]
    return value


def _serialize(value):
    """Marshal one Python value, floats included."""
    return _marshal(_decimals(value))


def _now() -> str:
    """ISO-8601 with microseconds, always UTC.

    Microseconds because this is the timestamp the reel sorts on, and a run
    writes its whole output inside one second — a one-second clock would tie
    almost everywhere and `browse._sort_records` would need a tie-break.
    """
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


#: The same clock every row is stamped with, for the callers outside this module
#: that need one: a submission records WHEN, and so does a cut. A timestamp
#: minted anywhere else would be a second clock to reconcile.
now = _now


def _node_pk(node_id: str) -> str:
    return f"NODE#{node_id}"


def _name_sk(name: str) -> str:
    return f"NAME#{name}"


def _lib_pk(lib: str) -> str:
    """The library's own partition.

    The same text a membership row carries as its *sort* key, and that the two
    agree is the mechanism rather than a coincidence: a membership is filed under
    the *user*, so the inverted `by-sk` index reaches every member of a library by
    asking for the string the library itself is keyed on. `scripts/add-member.sh`
    is what asks that question.
    """
    return f"LIB#{lib}"


def _user_pk(sub: str) -> str:
    return f"USER#{sub}"


def _item(attributes: dict) -> dict:
    """Marshal a plain mapping into DynamoDB's typed form.

    `None` is dropped rather than written as NULL: a folder has no `blob_key`,
    and an absent attribute is what `attribute_not_exists` and every reader here
    already understand.
    """
    return {key: _serialize(value) for key, value in attributes.items() if value is not None}


def _attributes(item: dict) -> dict:
    """Unmarshal one item, keys and all."""
    return {key: _deserialize(value) for key, value in item.items()}


def _record(item: dict) -> dict:
    """Unmarshal one item as a node record, with `size` back to an int.

    `pk` and `sk` are dropped because they are the layout, and the layout does
    not leave this module. The deserialiser hands back `Decimal` for every N,
    which is right for money and wrong for a byte count that is about to be
    JSON-encoded into a response.
    """
    record = _attributes(item)
    record.pop("pk", None)
    record.pop("sk", None)
    if "size" in record:
        record["size"] = int(record["size"])
    return record


def child_path(record: dict) -> str:
    """The `path` every child of this node carries.

    Public because `subtree` takes a path rather than a node — it is a GSI query
    and the index is on `lib` and `path` — so a caller that has a node and wants
    its branch needs this to bridge the two. Keeping the arithmetic in one place
    is also what stops a caller from inventing a slightly different form of the
    same string.
    """
    return f"{record['path']}{record['node_id']}/"


# ──────────────────────────── reads ────────────────────────────


def _pages(**kwargs):
    """Every page of one query.

    Paginated rather than single-shot because DynamoDB's 1 MB page is measured
    in bytes read, not items returned: a filtered query can come back empty with
    a `LastEvaluatedKey` still set, and code that trusted the first page would
    report an empty folder for a full one.

    A generator so a bounded caller can stop asking. Abandoning it mid-branch is
    what makes `_records_from`'s limit a limit on *round trips* rather than on
    the list it hands back.
    """
    try:
        yield from dynamodb.client().get_paginator("query").paginate(**kwargs)
    except ClientError as exc:
        logger.warning("Query failed (%s): %s", kwargs.get("IndexName", "table"), exc)
        raise UpstreamError("Could not read the catalog") from exc


def _query(**kwargs) -> list[dict]:
    """Every item one query returns, unfiltered and unbounded."""
    return [item for page in _pages(**kwargs) for item in page.get("Items", [])]


def _records_from(limit: int, **kwargs) -> tuple[list[dict], bool]:
    """The `META` records one query returns, and whether it was cut short.

    **Both halves of a node sit in `by-path` and `by-recent`** — the by-parent
    item carries `lib`, `path` and `created_at` too — so an unfiltered query
    returns a node twice, once complete and once as a projection. `META` is the
    half that is the record.

    The limit therefore counts *records* and not items. Counting items would
    bound a listing at roughly half the nodes it names, and would do it
    differently depending on how many of them are the library root, which has no
    by-parent half at all.
    """
    records: list[dict] = []
    for page in _pages(**kwargs):
        for item in page.get("Items", []):
            if _deserialize(item["sk"]) != META:
                continue
            if len(records) >= limit:
                return records, True
            records.append(_record(item))
    return records, False


def libraries_for(sub: str) -> list[dict]:
    """The libraries one Cognito `sub` is a member of.

    The membership row and nothing else — the library's *name* lives on the
    `LIB#<id>`/`META` item, and fetching it here would be a read per library for
    a caller that may only want to check access. Whoever needs the names asks
    for them.
    """
    items = _query(
        TableName=config.catalog_table(),
        KeyConditionExpression="pk = :pk",
        ExpressionAttributeValues={":pk": {"S": _user_pk(sub)}},
    )
    rows = [_attributes(item) for item in items]
    return [
        {
            "lib": row["sk"].split("#", 1)[1],
            "role": row.get("role"),
            "created_at": row.get("created_at"),
        }
        for row in rows
    ]


def library(lib: str) -> dict:
    """One library's own record: its name, and the node it opens on.

    Separate from `libraries_for` for the reason stated there — a membership row
    carries neither of those, and reading them for every membership would spend
    a read per library on the callers that only want to know whether this one is
    theirs. This is the other half of "whoever needs the names asks for them".

    Raises rather than returning `None`, like `node`. A library id naming no row
    is a caller's typo or a membership pointing at nothing, and both end
    whatever was being attempted — with the single exception of
    `GET /api/libraries`, which carries on and says why where it catches this.
    """
    try:
        response = dynamodb.client().get_item(
            TableName=config.catalog_table(),
            Key={"pk": {"S": _lib_pk(lib)}, "sk": {"S": META}},
        )
    except ClientError as exc:
        logger.warning("GetItem failed for %s: %s", lib, exc)
        raise UpstreamError("Could not read the catalog") from exc

    item = response.get("Item")
    if not item:
        raise NotFoundError(lib)
    return _record(item)


def node(node_id: str) -> dict:
    """One node's full record, by id.

    Raises rather than returning `None`: every caller in this module treats a
    missing node as the end of the request, and the routes above map
    `NotFoundError` to 404 already.
    """
    try:
        response = dynamodb.client().get_item(
            TableName=config.catalog_table(),
            Key={"pk": {"S": _node_pk(node_id)}, "sk": {"S": META}},
        )
    except ClientError as exc:
        logger.warning("GetItem failed for %s: %s", node_id, exc)
        raise UpstreamError("Could not read the catalog") from exc

    item = response.get("Item")
    if not item:
        raise NotFoundError(node_id)
    return _record(item)


def _batch_get(keys: list[dict]) -> list[dict]:
    """One `BatchGetItem`, asked again until nothing is left unprocessed.

    **`UnprocessedKeys` is not an exception, and that is the whole hazard.**
    DynamoDB answers a throttled or oversized batch with HTTP 200, the items it
    did read, and the keys it did not — so botocore's retry policy, which fires
    on error codes, never sees it. Code that took `Responses` and moved on would
    drop nodes from a folder listing at exactly the moment the table was busiest,
    and would do it silently.

    Bounded rather than looped forever: a request is being waited on, and a
    partition that has not cleared after four tries is an upstream problem the
    caller should hear about rather than a delay to absorb. Giving up raises,
    because the alternative — returning what did arrive — is the silent
    short listing this function exists to prevent.
    """
    table = config.catalog_table()
    items: list[dict] = []
    pending = {table: {"Keys": keys}}

    for attempt in range(BATCH_GET_ATTEMPTS):
        if attempt:
            time.sleep(BATCH_GET_BACKOFF * 2 ** (attempt - 1))
        try:
            response = dynamodb.client().batch_get_item(RequestItems=pending)
        except ClientError as exc:
            logger.warning("BatchGetItem failed: %s", exc)
            raise UpstreamError("Could not read the catalog") from exc

        items.extend(response.get("Responses", {}).get(table, []))
        pending = response.get("UnprocessedKeys") or {}
        if not pending:
            return items

    logger.warning("BatchGetItem gave up with %d keys unread", len(pending[table]["Keys"]))
    raise UpstreamError("Could not read the catalog")


def records(node_ids: list[str]) -> dict[str, dict]:
    """Full records for many nodes at once, keyed by id.

    **This exists because `children` cannot answer with `size` or
    `content_type`.** The by-parent item carries the index projection and
    nothing more, so a listing that wants a file's size is one query
    for the folder plus `ceil(n / 100)` batched reads for the records — and that
    is the shape to keep. Widening the projection would remove the batch and put
    a second copy of every mutable attribute on a second item, which every
    rename and every text edit would then have to keep in step. A stale byte
    count in a listing is worse than an extra round trip, and unlike the round
    trip it is invisible.

    Keyed by id rather than returned as a list because a batch answers in
    whatever order it likes: the caller holds the order it wants — `children`
    hands back name-ascending — and looks each record up.

    Duplicate ids are collapsed before the call. `BatchGetItem` rejects a
    request that names one key twice, and a caller merging two listings has no
    reason to know that.
    """
    wanted = list(dict.fromkeys(node_ids))
    found: dict[str, dict] = {}
    for start in range(0, len(wanted), BATCH_GET_KEYS):
        keys = [
            {"pk": {"S": _node_pk(node_id)}, "sk": {"S": META}}
            for node_id in wanted[start : start + BATCH_GET_KEYS]
        ]
        for item in _batch_get(keys):
            record = _record(item)
            found[record["node_id"]] = record
    return found


def children(parent_id: str) -> list[dict]:
    """One folder's contents, name-ascending.

    This reads the by-parent items, so what comes back is the **index
    projection** — `node_id`, `lib`, `kind`, `path`, `created_at`, plus the
    `name` carried in the sort key — and not the full record. A caller that
    needs `blob_key` or `size` for one entry fetches it with `node`.

    Deliberate: the projection is what makes a listing one query, and widening
    it would mean
    every rename and move keeps a second copy of the file's metadata in step.

    The order is free. DynamoDB returns a partition sorted by sort key, and the
    sort key is `NAME#<name>`, so a folder listing arrives name-ascending
    without a sort — which is two of the four orders `browse.SORTS` offers.
    Missing folders are not an error here; `browse` is forgiving on reads and so
    is this.
    """
    items = _query(
        TableName=config.catalog_table(),
        KeyConditionExpression="pk = :pk AND begins_with(sk, :name)",
        ExpressionAttributeValues={":pk": {"S": _node_pk(parent_id)}, ":name": {"S": "NAME#"}},
    )
    entries = []
    for item in items:
        record = _record(item)
        record["name"] = _deserialize(item["sk"]).split("#", 1)[1]
        entries.append(record)
    return entries


def child_by_name(parent_id: str, name: str) -> dict:
    """The one child of a folder with this name, as the index projection.

    A `GetItem` and not a filtered `children`, because the by-parent item is
    keyed on exactly this question — `NODE#<parent>` and `NAME#<name>` are its
    full primary key — so a name walk costs one read per segment regardless of
    how many files the folder holds. That is what makes `/api/resolve` on a deep
    path affordable, and it is the same uniqueness that `_put_name`'s condition
    expression enforces on the way in: there cannot be two.

    The projection, not the record. A walk only needs the next `node_id`, and
    the caller that has arrived fetches the record with `node`. Raises
    `NotFoundError` naming the segment, like every other read here.
    """
    try:
        response = dynamodb.client().get_item(
            TableName=config.catalog_table(),
            Key={"pk": {"S": _node_pk(parent_id)}, "sk": {"S": _name_sk(name)}},
        )
    except ClientError as exc:
        logger.warning("GetItem failed for '%s' under %s: %s", name, parent_id, exc)
        raise UpstreamError("Could not read the catalog") from exc

    item = response.get("Item")
    if not item:
        raise NotFoundError(name)
    return {**_record(item), "name": name}


def branch(lib: str, path: str, limit: int) -> tuple[list[dict], bool]:
    """Every node beneath a path, as full records, stopping at `limit`.

    One `begins_with` on `by-path` reads a whole branch, which is what the
    materialised `path` is for. Pass `child_path(record)` to get a node's
    descendants; the node itself is not among them, because its own `path` names
    its ancestors and stops short.

    Returns whether it stopped early rather than deciding what that means. The
    two callers want opposite things — `subtree` turns it into a refusal,
    `browse.reel_items` into a page boundary — and a function that picked one
    would need a second copy of itself for the other.
    """
    return _records_from(
        limit,
        TableName=config.catalog_table(),
        IndexName=BY_PATH_INDEX,
        KeyConditionExpression="lib = :lib AND begins_with(#path, :path)",
        ExpressionAttributeNames={"#path": "path"},
        ExpressionAttributeValues={":lib": {"S": lib}, ":path": {"S": path}},
    )


def recent(lib: str, limit: int) -> tuple[list[dict], bool]:
    """Every image and video in a library, newest first, stopping at `limit`.

    The only read here that returns rows in an order the *table* chose rather
    than one the caller sorted for. `browse.reel_items` is the caller: a reel
    over a whole library wants the newest of it, and `by-path` cannot answer
    that — its range key is an ancestor list, so its order is the tree's.

    **Every row this returns is already something the reel can show.**
    `by-recent` is hashed on the sparse `reel` attribute, so a
    folder, an entity record and a library index row are absent from it rather
    than read and discarded — and the `limit` above is therefore spent on media
    instead of on whatever the tree happened to hold.

    **Descending, and that is what makes truncating safe.** What a cut drops is
    the oldest rows, which is the tail a reel was never going to reach; cutting
    a `by-path` query drops an arbitrary branch instead.
    """
    return _records_from(
        limit,
        TableName=config.catalog_table(),
        IndexName=BY_RECENT_INDEX,
        KeyConditionExpression="#reel = :lib",
        ExpressionAttributeNames={"#reel": REEL_ATTRIBUTE},
        ExpressionAttributeValues={":lib": {"S": lib}},
        ScanIndexForward=False,
    )


def subtree(lib: str, path: str) -> list[dict]:
    """`branch`, with the cap as a refusal rather than a limit.

    **The refusal is the point**, and it is inherited deliberately from
    `manage._subtree`. Both callers of this function are writes: a move rewrites
    every descendant's `path` and a delete removes every descendant's rows. A
    truncated answer to either is the setup for doing half the job and reporting
    success. `browse.reel_items` reads `branch` directly for exactly the opposite
    reason — a page of a library is allowed to be shorter than the library.
    """
    cap = config.max_folder_objects()
    records, truncated = branch(lib, path, cap + 1)
    if truncated or len(records) > cap:
        raise ValidationError(
            f"this folder holds more than {cap} items — "
            "move or delete it in smaller pieces"
        )
    return records


# ──────────────────────────── writes ────────────────────────────


def _write(steps: list[tuple[dict, Exception | None]]) -> None:
    """Apply one transaction, and turn each condition failure into its own error.

    A step is the `TransactItems` entry plus the exception to raise if *that*
    entry's condition is the one that failed. Pairing them is what lets a
    put-if-absent on a `NAME#` item mean "that name is taken" (409) while the
    `attribute_exists` guard on a record in the same transaction means "the node
    is missing" (404) — DynamoDB reports which item was cancelled and in which
    position, and throwing that away would collapse both onto one status.

    A step with no exception is one that carries no condition and so can never
    be the cancelled item; the deletes below are all of that kind.

    Anything the reasons cannot explain is upstream: a throttle, a transaction
    conflict with another writer, a table that is not there.
    """
    try:
        dynamodb.client().transact_write_items(TransactItems=[item for item, _ in steps])
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "TransactionCanceledException":
            logger.warning("TransactWriteItems failed: %s", exc)
            raise UpstreamError("Could not write to the catalog") from exc

        reasons = exc.response.get("CancellationReasons") or []
        for (_, failure), reason in zip(steps, reasons):
            if failure is not None and reason.get("Code") == "ConditionalCheckFailed":
                raise failure from exc

        logger.warning("TransactWriteItems cancelled: %s", reasons)
        raise UpstreamError("Could not write to the catalog") from exc


def _put_name(record: dict, *, parent_id: str, name: str) -> dict:
    """The by-parent half of a node, put only if that name is free."""
    return {
        "Put": {
            "TableName": config.catalog_table(),
            "Item": _item(
                {
                    "pk": _node_pk(parent_id),
                    "sk": _name_sk(name),
                    "node_id": record["node_id"],
                    "lib": record["lib"],
                    "kind": record["kind"],
                    "path": record["path"],
                    "created_at": record["created_at"],
                }
            ),
            "ConditionExpression": "attribute_not_exists(pk)",
        }
    }


def _delete_name(*, parent_id: str, name: str) -> dict:
    """Drop a by-parent item.

    Unconditional on purpose. It is only ever paired with the put that replaces
    it, and a condition here would report "already deleted" as the *collision*
    error belonging to that put — the wrong message for a state that is already
    what the caller asked for.
    """
    return {
        "Delete": {
            "TableName": config.catalog_table(),
            "Key": {"pk": {"S": _node_pk(parent_id)}, "sk": {"S": _name_sk(name)}},
        }
    }


def _delete_meta(node_id: str) -> dict:
    return {
        "Delete": {
            "TableName": config.catalog_table(),
            "Key": {"pk": {"S": _node_pk(node_id)}, "sk": {"S": META}},
        }
    }


def _update(key: dict, assignments: dict) -> dict:
    """Set named attributes on an item that already exists.

    Every attribute goes through `ExpressionAttributeNames`, because `name`,
    `path` and `size` are all DynamoDB reserved words and half of this module's
    updates would otherwise be a syntax error found at runtime. Numbering the
    placeholders rather than deriving them from the attribute keeps that true
    for whatever gets assigned next.

    `attribute_exists(pk)` because an update in DynamoDB creates the item when
    it is missing. Every caller here is changing something it has already read,
    so a vanished item is a 404 and never a fresh row with three attributes on
    it.
    """
    names = {f"#{index}": attribute for index, attribute in enumerate(assignments)}
    values = {
        f":{index}": _serialize(value)
        for index, value in enumerate(assignments.values())
        if value is not None
    }

    # **A `None` is a REMOVE, not a NULL**, and it is the same rule `_item`
    # follows on the way in: an absent attribute is what `attribute_not_exists`
    # and every reader here already understand. It is load-bearing for the
    # sparse `reel` key — renaming `clip.png` to `clip.txt` has to take the row
    # *out* of `by-recent`, and writing NULL would leave it in the index
    # advertising a file the reel cannot draw.
    clauses = []
    if values:
        clauses.append("SET " + ", ".join(f"{k} = :{k[1:]}" for k in names if f":{k[1:]}" in values))
    removed = [k for k in names if f":{k[1:]}" not in values]
    if removed:
        clauses.append("REMOVE " + ", ".join(removed))

    update = {
        "TableName": config.catalog_table(),
        "Key": key,
        "UpdateExpression": " ".join(clauses),
        "ExpressionAttributeNames": names,
        "ConditionExpression": "attribute_exists(pk)",
    }
    if values:
        update["ExpressionAttributeValues"] = values
    return {"Update": update}


def _update_meta(node_id: str, assignments: dict) -> dict:
    return _update({"pk": {"S": _node_pk(node_id)}, "sk": {"S": META}}, assignments)


def _update_name(*, parent_id: str, name: str, assignments: dict) -> dict:
    """Change an attribute on the by-parent half of a node.

    Only `path` is ever assigned through here, by a move. It is an update rather
    than a put because the item is already there and its name is not changing —
    `_put_name`'s `attribute_not_exists` guard would refuse it, correctly, since
    that guard is the collision check.
    """
    return _update({"pk": {"S": _node_pk(parent_id)}, "sk": {"S": _name_sk(name)}}, assignments)


def _folder_node(node_id: str) -> dict:
    """A node that is allowed to have children.

    Nothing in the key layout stops a `NAME#` item being written under a file's
    id — `pk` is just `NODE#<id>` either way — so the only thing keeping a file
    from growing a subtree is this check, made by both operations that choose a
    parent.
    """
    record = node(node_id)
    if record["kind"] != KIND_FOLDER:
        raise ValidationError("a file cannot hold other nodes")
    return record


# ─────────────────────── who owns a node, and its key ───────────────────────
#
# **The owner is derived, never stored on the node.** A node's `path` is already
# the materialised list of ancestor ids, and an entity's root folder carries
# `entity: "<entity_id>"` — so the owner of any node is the deepest ancestor
# carrying that attribute, found in one `BatchGetItem` over a path this table
# already holds. Nothing new is written, nothing drifts, and a move that changes
# the owner is visible immediately.
#
# **The blob key is the opposite: stamped once, at creation, and never
# re-derived.** It carries the owner's id so a bucket listing is per-entity —
# Storage Lens cost, lifecycle rules, a bulk delete that is one prefix — and
# carries no name, so a listing of the PRODUCTION bucket cannot leak hard
# rule #1. That rule is env-scoped — a dev subject may be named in the repo —
# and a production character may not be named anywhere, including in a key
# nobody thought of as prose.
#
# The honest cost, stated where somebody would be tempted to fix it: move a file
# from a character to a project and its key keeps the old prefix. The key is
# still correct — it is a pointer — but it now *looks* like it means something it
# does not. `studio catalog reseat` rewrites drifted keys out of band. **Nothing
# in this module may re-derive a key for a node that has one**, because a
# presigned URL, a copy and a delete all name the recorded string and a second
# opinion about it is a lost object.

# What a character's and a project's bytes are filed under. Three prefixes in the
# bucket and nothing else; anything owned by neither is the library's.
OWNER_PREFIXES = {ENTITY_CHARACTER: "characters", ENTITY_PROJECT: "projects"}
LIBRARY_PREFIX = "libraries"

# The second segment of every key this API stamps: an entity or library id.
#
# Matched by PREFIX rather than by a uuid pattern, which is how an id is
# recognised everywhere else here (`startswith("proj-")` in the CLI resolvers,
# `entity_kind` on the same split). Pinning a uuid length would make this the
# one place that disagrees about what an id looks like.
_ID_PREFIXES = ("char-", "proj-", "lib-")


def blob_key_for(node_id: str, name: str, owner_kind: str | None, owner_id: str) -> str:
    """Where a node's bytes live: `<owner_kind>/<owner_id>/<node_id>.<ext>`.

    **The single definition, and the only place this string is ever built.** The
    upload route signs for it, `create_node` records it, `confirm-upload` heads
    it; three callers computing it independently is three chances to disagree
    about a value a signature is scoped to.

    The extension is decoration for a human reading the S3 console. `content_type`
    on the row is authoritative and the API sets it on every presigned response —
    so a node with no extension gets a key with none, and nothing anywhere reads
    one back off a key.

    `owner_kind` is a run, a scene or a movie for plenty of nodes, and none of
    those gets a prefix of its own: they live inside a project and their bytes
    are the project's. Only the two entity kinds in `OWNER_PREFIXES` own bytes,
    and everything else falls through to the library.
    """
    prefix = OWNER_PREFIXES.get(owner_kind, LIBRARY_PREFIX)
    return f"{prefix}/{owner_id}/{node_id}{keys.extension(name)}"


def is_api_blob(record: dict) -> bool:
    """Whether this node's bytes were written through this API.

    **It reads the SHAPE of the first two segments and nothing else**:
    `<owner_prefix>/<entity-or-library id>/…` — one of the three prefixes, then
    an id. The tail is not read: a key's last segment is `<node_id>.<ext>` when
    `blob_key_for` stamped it and may be a descriptive name in a library
    `studio catalog reseat` has not been run against, and both are keys this
    API wrote.

    **It is not a check on WHICH owner.** The prefix says who owned the node
    when the key was stamped and drifts the moment the node moves, so reading
    the id itself would start refusing uploads to a file somebody dragged into
    another folder. Only the shape is read; the values are not.

    The two upload routes share this so they cannot disagree about which objects
    are writable through a signature — a distinction a signed URL makes permanent
    the moment it is handed out. A key of any other shape was not written by
    this API, and overwriting such bytes is not what those routes are for.
    """
    blob_key = record.get("blob_key")
    if not blob_key:
        return False
    segments = blob_key.split("/")
    return (len(segments) >= 3
            and segments[0] in set(OWNER_PREFIXES.values()) | {LIBRARY_PREFIX}
            and segments[1].startswith(_ID_PREFIXES))


def entity_chain(record: dict) -> list[str]:
    """Every entity this node sits inside, deepest first, itself included.

    One `BatchGetItem` over the ids in `path`, which is why the materialised
    index earns its keep a second time: the alternative is a `GetItem` per level,
    sequentially, because each parent's id is only known once its child has been
    read.

    Deepest first because both callers want the nearest answer and differ only in
    which kinds they will accept — `owner_of` takes the first of any kind, and
    `_blob_owner` takes the first that is a character or a project.
    """
    ancestors = [node_id for node_id in record.get("path", "").split("/") if node_id]
    chain = [record["entity"]] if record.get("entity") else []
    if not ancestors:
        return chain

    found = records(ancestors)
    for node_id in reversed(ancestors):
        ancestor = found.get(node_id)
        if ancestor and ancestor.get("entity"):
            chain.append(ancestor["entity"])
    return chain


def owner_of(record: dict) -> dict | None:
    """The entity a node belongs to, as `{kind, id, name}`, or `None`.

    What the SPA shows as "in <project>", and what `GET /api/nodes/<id>/owner`
    answers. A node directly under the library root belongs to nobody in
    particular, which is a real answer and not a missing one — folders a person
    makes by hand are meant to be reachable without becoming somebody's.

    The deepest entity wins, so a run's output reports the run rather than the
    project it sits in. That is the answer a person wants from a file, and the
    project is one hop up its `path` for anyone who wants that instead.
    """
    for entity_id in entity_chain(record):
        try:
            return entity_summary(entity_id)
        except (NotFoundError, ValidationError):
            # A reverse pointer naming a record that does not exist. Skipped rather than
            # raised: the node is fine, and a listing that 500s because one
            # ancestor was half-deleted is a worse answer than "owned by nobody".
            logger.warning("Node %s names a missing entity: %s", record["node_id"], entity_id)
    return None


def _blob_owner(record: dict) -> tuple[str | None, str]:
    """The kind and id a new node's blob key is stamped from.

    Only a character or a project owns bytes. A run, a scene and a movie all live
    inside a project and their outputs are the project's — which is what keeps
    the bucket at three prefixes rather than six.
    """
    for entity_id in entity_chain(record):
        kind = entity_kind(entity_id)
        if kind in OWNER_PREFIXES:
            return kind, entity_id
    return None, record["lib"]


def _reel_value(name: str, lib: str) -> str | None:
    """The sparse index key, or nothing.

    Returning `None` rather than omitting the call at each site is what makes
    `_item`'s "drop the nulls" rule do the work: an attribute that is absent
    keeps the row out of `by-recent`, and there is one expression of that rule
    instead of one per writer.
    """
    return lib if keys.kind(name) in REEL_KINDS else None


def _new_node(
    parent: dict,
    name: str,
    kind: str,
    *,
    node_id: str | None = None,
    entity: str | None = None,
    blob_key: str | None = None,
    size: int | None = None,
    content_type: str | None = None,
    checksum: str | None = None,
    description: str | None = None,
    tags: list | None = None,
) -> dict:
    """One node record, ready to be written as its two items.

    Factored out because the entity creates below build five, six or ten node
    records inside one transaction and must build them exactly the way
    `create_node` does. A second spelling of this dict is a character whose pool
    folders are subtly not folders.

    `node_id` is passed in only by those creates, which need the id before the
    transaction is composed — a character's root has to be named by the character
    record in the same write that creates it.
    """
    now = _now()
    node_id = node_id or f"node-{uuid.uuid4()}"
    return {
        "node_id": node_id,
        "parent_id": parent["node_id"],
        "lib": parent["lib"],
        "name": name,
        "kind": kind,
        "entity": entity,
        "blob_key": blob_key,
        "size": size,
        "content_type": content_type,
        "description": description,
        "tags": tags or None,
        "reel": _reel_value(name, parent["lib"]) if kind == KIND_FILE else None,
        "path": child_path(parent),
        "created_at": now,
        "updated_at": now,
    }


def _node_steps(record: dict) -> list[tuple[dict, Exception | None]]:
    """The two writes that are one node, both conditional on nothing existing."""
    taken = ConflictError(f"'{record['name']}' already exists here")
    return [
        (_put_name(record, parent_id=record["parent_id"], name=record["name"]), taken),
        (
            {
                "Put": {
                    "TableName": config.catalog_table(),
                    "Item": _item({"pk": _node_pk(record["node_id"]), "sk": META, **record}),
                    # A v4 UUID cannot realistically collide, so this guard never
                    # fires — it is here so that no put in this module is capable
                    # of overwriting a record, which is the property worth being
                    # able to state without exceptions.
                    "ConditionExpression": "attribute_not_exists(pk)",
                }
            },
            taken,
        ),
    ]


def create_node(
    parent_id: str,
    raw_name: str | None,
    kind: str,
    *,
    blob_key: str | None = None,
    size: int | None = None,
    content_type: str | None = None,
    owner: tuple[str | None, str] | None = None,
    description: str | None = None,
    tags: list | None = None,
) -> dict:
    """Add a folder or a file under an existing parent.

    **The library is read off the parent rather than passed in.** A `lib`
    argument would be a second source of truth for the one attribute every GSI
    partitions on, and a caller that got it wrong would produce a node that is
    listed in one library's subtree and owned by another. The parent already
    knows, so it is asked.

    A folder is refused a `blob_key`, which is the whole of the distinction:
    a folder is a node with no blob. Size and content type are
    optional because the caller writing the object may not know either yet —
    `set_blob` fills them in later.

    **A file may omit `blob_key`, and then one is stamped from the owner the
    parent resolves to** — `<owner_kind>/<owner_id>/<node_id>.<ext>`. A client
    cannot name that key itself because it does not know the node id yet, so the
    only way to have an id-derived key is for this function to mint both
    together. Until the bytes land the node has a key and no object behind it —
    nothing can download it (`browse._blob_at` 404s) and the reel skips it, and
    `browse.is_abandoned_upload` keeps it out of a listing rather than drawing a
    tile that will not load.

    **`owner` is a cache and never a second opinion.** Resolving it costs one
    batched read of the parent's ancestors, which is nothing for one node and is
    a read per file for a bulk copy of forty — so `manage.copy_objects` resolves
    the destination once and hands it in. A caller that passes a *different*
    owner is filing bytes under an entity that does not hold the node, so the
    only thing that may compute one is `_blob_owner`.

    An explicit `blob_key` is stored exactly as given: a key is a pointer, and
    this module never forms a second opinion about one it did not mint.
    """
    if kind not in KINDS:
        raise ValidationError(f"kind must be one of {', '.join(sorted(KINDS))}")
    if kind == KIND_FOLDER and blob_key:
        raise ValidationError("a folder cannot carry a blob_key")

    name = keys.clean_name(raw_name)
    parent = _folder_node(parent_id)
    record = _new_node(parent, name, kind, size=size, content_type=content_type,
                       description=description, tags=clean_tags(tags) or None)

    if kind == KIND_FILE:
        owner_kind, owner_id = owner if owner is not None else _blob_owner(parent)
        record["blob_key"] = blob_key or blob_key_for(
            record["node_id"], name, owner_kind, owner_id
        )
    else:
        record["blob_key"] = None

    _write(_node_steps(record))

    logger.info("Created %s %s under %s", kind, record["node_id"], parent_id)
    return {key: value for key, value in record.items() if value is not None}


def blob_owner_for(parent_id: str) -> tuple[str | None, str]:
    """The owner a file created under this folder would be stamped from.

    Public so a bulk write can resolve it once. `manage.copy_objects` copies
    forty files into one folder; without this every one of them pays a batched
    read of the same ancestry to reach the same answer.
    """
    return _blob_owner(node(parent_id))


def create_numbered(parent_id: str, raw_name: str | None, kind: str) -> dict:
    """`create_node`, but a taken name is numbered instead of refused.

    `clip.mp4` arriving beside a `clip.mp4` becomes `clip (2).mp4` — the form
    `keys.numbered_name` owns and `manage.copy_nodes` produces.
    Nothing is overwritten in any branch, and nothing is refused for a clash.

    **Retry-on-conflict, not list-then-choose, and the difference is the whole
    reason this is a function rather than two lines at a call site.** Reading the
    destination's names first and picking a free one describes a folder as it was
    a moment ago: the pipeline records runs into the same table, and a browser
    uploading five files is five round trips during which that snapshot ages. The
    conditional put on the `NAME#` item is the only authority on whether a name is
    free, so this asks *it*, and a loser of a race simply takes the next number.
    It also costs nothing in the ordinary case — one write, no query — where a
    listing would cost a query per file.

    **Numbering consults names and nothing else.** Not sizes, not checksums: an
    upload of the same bytes twice is two files, the same bargain
    `manage.copy_objects` documents at length. "Has this been done already" is
    not a question this service answers.

    The bound is `keys.MAX_NAME_VARIANTS`, shared with copy so one folder cannot
    accept `(100)` from one entry point and refuse it from the other.
    """
    name = keys.clean_name(raw_name)
    for attempt in range(1, keys.MAX_NAME_VARIANTS + 1):
        candidate = name if attempt == 1 else keys.numbered_name(name, attempt)
        try:
            return create_node(parent_id, candidate, kind)
        except ConflictError:
            continue

    raise ConflictError(
        f"'{name}' already names {keys.MAX_NAME_VARIANTS} files here — "
        "rename some of them first"
    )


#: A description is prose for a person and for a prompt, not a field anything
#: parses. Capped only so one paste cannot make a listing unreadable.
MAX_DESCRIPTION = 2000
#: Free-form on purpose. A per-library vocabulary would make filtering reliable
#: and would be a second thing to keep correct; the reference tags a
#: `--pick-tag` filter matches are free-form and converge without one.
MAX_TAGS = 32
MAX_TAG = 40


def clean_tags(raw) -> list[str]:
    """A tag list, de-duplicated and order-preserving, or a refusal.

    **Case-folded and trimmed, because a tag is a selector.** `Poolside` and
    `poolside ` filtering as two different things is a bug a person cannot see —
    they look identical in a chip. The one place this is felt is the reference
    index, where `--pick-tag face` already has to match what somebody typed
    months ago.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValidationError("tags must be a list")
    seen, out = set(), []
    for entry in raw:
        if not isinstance(entry, str):
            raise ValidationError("every tag must be a string")
        tag = " ".join(entry.split()).lower()
        if not tag:
            continue
        if len(tag) > MAX_TAG:
            raise ValidationError(f"tag longer than {MAX_TAG} characters: {tag[:20]}…")
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    if len(out) > MAX_TAGS:
        raise ValidationError(f"more than {MAX_TAGS} tags")
    return out


def describe_node(node_id: str, *, description=..., tags=...) -> dict:
    """What a file SHOWS, on the file — one row, no objects, no bytes.

    **This is the whole write path for what a picture is.** A description and
    its tags are attributes of the file, never of a relationship the file is in:
    "head and shoulders in full profile" is true of the picture whether or not
    anybody ever makes it identity, so what a picture IS and what it is FOR both
    live here.

    A sentinel default rather than `None` for both arguments, because `None` is
    a value here: sending `description=None` clears it, and omitting it leaves
    what is there. `_update` already turns a `None` into a REMOVE.
    """
    assignments = describe_assignments(description, tags)
    if not assignments:
        raise ValidationError("send description or tags")

    record = node(node_id)
    assignments["updated_at"] = _now()
    _write([(_update_meta(node_id, assignments), None)])
    return {**record, **assignments}


def describe_assignments(description=..., tags=...) -> dict:
    """The validated attributes a describe writes, shared by both writers.

    One validator, wherever a tag is typed: the file browser, the picker's
    filter and the CLI all fold the same way, so `Face` and `face ` are the tag
    `face` and a filter matches what a person believes they wrote.
    """
    assignments: dict = {}
    if description is not ...:
        if description is not None:
            if not isinstance(description, str):
                raise ValidationError("description must be a string")
            description = description.strip()
            if len(description) > MAX_DESCRIPTION:
                raise ValidationError(f"description longer than {MAX_DESCRIPTION} characters")
        assignments["description"] = description or None
    if tags is not ...:
        assignments["tags"] = clean_tags(tags) or None
    return assignments


def rename_node(node_id: str, raw_name: str | None) -> dict:
    """Give a node a new name inside the same parent.

    Three items, one transaction: the old by-parent entry goes, the new one
    arrives under `attribute_not_exists`, and the record's `name` is updated.
    `path` is untouched — it names ancestors, and a rename changes none of them,
    which is the same separation `manage.rename_object` and `manage.move_objects`
    hold on the S3 side.
    """
    record = node(node_id)
    parent_id = record.get("parent_id")
    if not parent_id:
        raise ValidationError("the library root cannot be renamed")

    name = keys.clean_name(raw_name)
    if name == record["name"]:
        return {**record, "renamed": False}

    now = _now()
    updated = {**record, "name": name, "updated_at": now}

    # **A rename can change what a file *is*.** `reel` is written from the
    # extension, so `clip.png` renamed to `clip.txt` has to leave `by-recent` and
    # the reverse has to join it. Only for a file: a folder is never in that
    # index and assigning the attribute to it would put it there.
    assignments = {"name": name, "updated_at": now}
    if record["kind"] == KIND_FILE:
        assignments["reel"] = _reel_value(name, record["lib"])
        updated["reel"] = assignments["reel"]

    _write(
        [
            (_delete_name(parent_id=parent_id, name=record["name"]), None),
            (
                _put_name(updated, parent_id=parent_id, name=name),
                ConflictError(f"'{name}' already exists here"),
            ),
            (_update_meta(node_id, assignments), NotFoundError(node_id)),
        ]
    )

    logger.info("Renamed %s -> %s", node_id, name)
    return {**updated, "renamed": True}


def move_node(node_id: str, parent_id: str) -> dict:
    """Carry a node, and everything beneath it, under a different parent.

    Zero objects move. What changes is one `parent_id`, one by-parent item, and
    the derived `path` on every descendant.

    **Two writes, in this order, and the order is the interesting part.** The
    first transaction is the move itself — the by-parent swap and the new
    `parent_id` — and the rest rewrite descendants' `path` fifty nodes at a
    time. `TransactWriteItems` caps at a hundred items, so a subtree of any size
    cannot be one transaction, and something has to be allowed to be
    half-applied. `path` is the safe half: it is derivable from `parent_id`, so
    an interrupted move leaves an index that can be rebuilt. Doing it the other
    way round would leave descendants indexed under a branch their parent
    pointers do not agree with, and nothing to say which was right.

    The refusals are the same two `manage.move_folder` makes, for the same
    reasons: a node cannot be moved inside itself (there the copy loop would
    feed itself; here the subtree would contain its own ancestor), and a name
    already taken at the destination refuses the whole request rather than
    merging two trees. Crossing libraries is refused as well: a move that could
    change `lib` would change who can reach the branch, which no membership check
    on a move asks about.
    """
    record = node(node_id)
    if not record.get("parent_id"):
        raise ValidationError("the library root cannot be moved")
    if parent_id == record["parent_id"]:
        return {**record, "moved": False, "descendants": 0}

    destination = _folder_node(parent_id)
    branch = child_path(record)
    if parent_id == node_id or destination["path"].startswith(branch):
        raise ValidationError("a folder cannot be moved inside itself")
    if destination["lib"] != record["lib"]:
        raise ValidationError("a node cannot be moved into another library")

    descendants = subtree(record["lib"], branch)
    now = _now()
    moved = {**record, "parent_id": parent_id, "path": child_path(destination), "updated_at": now}

    _write(
        [
            (_delete_name(parent_id=record["parent_id"], name=record["name"]), None),
            (
                _put_name(moved, parent_id=parent_id, name=record["name"]),
                ConflictError(f"'{record['name']}' already exists there"),
            ),
            (
                _update_meta(
                    node_id, {"parent_id": parent_id, "path": moved["path"], "updated_at": now}
                ),
                NotFoundError(node_id),
            ),
        ]
    )

    _rewrite_branch(descendants, old=branch, new=child_path(moved))

    logger.info("Moved %s under %s (%d descendants)", node_id, parent_id, len(descendants))
    return {**moved, "moved": True, "descendants": len(descendants)}


def _rewrite_branch(descendants: list[dict], *, old: str, new: str) -> None:
    """Re-materialise `path` on a moved branch.

    Both halves of every node, because the by-parent item carries `path` too and
    `by-path` ranges on it. Two writes per descendant is what fixes the batch at
    fifty nodes.

    Only the prefix of `path` changes. The part below the moved node describes
    ancestors that moved with it and is copied across untouched. `lib` is never
    touched: a move stays inside one library or `move_node` refused.
    """
    steps: list[tuple[dict, Exception | None]] = []
    for record in descendants:
        path = new + record["path"][len(old):]
        assignments = {"path": path}
        steps.append(
            (
                _update_meta(record["node_id"], {**assignments, "updated_at": _now()}),
                NotFoundError(record["node_id"]),
            )
        )
        steps.append(
            (
                _update_name(
                    parent_id=record["parent_id"],
                    name=record["name"],
                    assignments=assignments,
                ),
                NotFoundError(record["node_id"]),
            )
        )

    for start in range(0, len(steps), TRANSACTION_ITEMS):
        _write(steps[start : start + TRANSACTION_ITEMS])


def _assert_no_entities(candidates: list[dict]) -> None:
    for victim in candidates:
        if victim.get("entity"):
            raise ValidationError(
                f"'{victim['name']}' is the folder of {victim['entity']} — "
                "delete the entity instead"
            )


def assert_deletable(record: dict) -> None:
    """Refuse now what `delete_node` would refuse later.

    **A bulk delete has to know before it starts.** `delete_node` makes this
    check from the subtree it is about to remove, which is the right place for
    it and the wrong time for a selection of forty: the eighth entry refusing
    leaves seven already gone. So `manage.delete_nodes` asks here first, for
    every record, and only then deletes any of them.

    A file cannot hold a descendant, so it is checked from the record in hand and
    costs nothing. A folder pays one `by-path` query, which is the same query the
    delete itself is about to make.
    """
    candidates = [record]
    if record["kind"] == KIND_FOLDER:
        candidates += subtree(record["lib"], child_path(record))
    _assert_no_entities(candidates)


def delete_node(node_id: str, *, allow_entities: bool = False) -> dict:
    """Remove a node and everything beneath it, and report the blobs it held.

    **Deepest first, the node itself last.** Batching means a subtree bigger
    than fifty nodes is several transactions, so an interruption is possible;
    deleting upwards means what survives is still a tree hanging off a parent
    that lists it, rather than a set of rows nothing can reach. Re-running the
    delete finishes the job.

    **A folder that is some entity's root is refused, and so is a folder holding
    one.** That is the single hard rule the "layout is convention" reading leaves
    (see `services.layout`): every other folder in a character or a project may
    be renamed, moved or deleted freely, because reference-ness and run-ness are
    row attributes now. The root is different only because a record names it, and
    a record naming a node that does not exist is the one broken state this
    model cannot repair from the tree. The refusal says which entity to delete
    instead.

    `allow_entities` is for the entity deletes themselves, which have already
    removed the record and its links and are finishing the job. It is not a
    force flag for a caller who finds the refusal inconvenient.

    Nothing in S3 is touched. The `blob_key` values come back so the caller can
    decide what to do about the bytes — two nodes may point at one key, since a
    copy in this model copies a row, so "is this blob now unreferenced" is not a
    question one delete can answer.

    **A sweep is opened before the first row goes.** The bytes are deleted by
    the caller after this returns, so an interruption in between would otherwise
    leave objects nothing named — findable only by listing the whole bucket
    against the whole table. The sweep records the same keys on a row first, so
    an interruption leaves a *pointer* to the orphans rather than orphans nobody
    can find. `sweep_id` comes back for the caller to close once the bytes are
    deleted; see `open_sweep`.
    """
    record = node(node_id)
    if not record.get("parent_id"):
        raise ValidationError("the library root cannot be deleted")

    descendants = subtree(record["lib"], child_path(record))
    if not allow_entities:
        _assert_no_entities([record, *descendants])
    descendants.sort(key=lambda entry: len(entry["path"]), reverse=True)
    doomed = descendants + [record]

    freed = [(victim["node_id"], victim["blob_key"])
             for victim in doomed if victim.get("blob_key")]
    sweep = open_sweep(record["lib"], freed)

    steps: list[tuple[dict, Exception | None]] = []
    for victim in doomed:
        steps.append((_delete_name(parent_id=victim["parent_id"], name=victim["name"]), None))
        steps.append((_delete_meta(victim["node_id"]), None))

    for start in range(0, len(steps), TRANSACTION_ITEMS):
        _write(steps[start : start + TRANSACTION_ITEMS])

    logger.info("Deleted %s (%d nodes)", node_id, len(doomed))
    return {
        "node_id": node_id,
        "lib": record["lib"],
        "deleted": len(doomed),
        "blob_keys": [key for _, key in freed],
        "sweep": sweep,
    }


# ───────────────────────────── sweeps ──────────────────────────────────────
#
# A sweep is the row that makes a delete recoverable without a bucket scan.
#
# WHY IT EXISTS
# -------------
# Rows are deleted first and bytes second, because the other order leaves a row
# pointing at a blob that has been deleted — a broken tile the user sees — while
# this order leaves an object no reader can reach. Without a sweep that leftover
# could only be found by listing every object in the bucket, scanning every row
# in the table and subtracting. So the keys are written to a row *before* the
# rows that name them are deleted, and the leftover is addressed rather than
# searched for.
#
# WHY THE DRAIN RE-CHECKS EVERY NODE
# ----------------------------------
# A sweep is opened before the deletes, so a crash *between* the two leaves a
# sweep naming keys whose rows are still live. Deleting those would be the worse
# bug the row-first order exists to avoid — so `drain` looks each node id up and
# keeps any key whose row is still there. That is a point read per key, batched,
# and it needs no index on `blob_key`: the sweep carries the node id precisely so
# this question can be asked backwards.
#
# It follows that draining is always safe, at any age, from any request, and
# twice concurrently: every step is idempotent and the recheck is the guard.

SWEEP_PREFIX = "SWEEP#"

#: One `DeleteObjects` call takes a thousand keys, so a sweep holds no more —
#: a sweep that could not be discharged in one call would need its own paging.
SWEEP_KEYS = 1000


def open_sweep(lib: str, freed: list[tuple[str, str]]) -> list[str]:
    """Record the blobs a delete is about to strand; answer with the rows written.

    `freed` is `(node_id, blob_key)` pairs. Both halves are stored: the key is
    what gets deleted, and the node id is what `drain` asks about to find out
    whether deleting it is still the right thing to do.

    **The sort keys come back, and closing takes them.** An opaque sweep id
    would make `close_sweep` *find* its own rows — a query of the whole library
    partition per close, and a bulk delete closes one sweep per node. A caller
    that just wrote a row knows where it is; making it say so turns the close
    into point deletes.

    Empty when there is nothing to record, so a folder-only delete writes no row.
    Most deletes in this library are folders.
    """
    if not freed:
        return []

    sweep_id = str(uuid.uuid4())
    now = _now()
    written: list[str] = []
    steps = []
    for start in range(0, len(freed), SWEEP_KEYS):
        chunk = freed[start : start + SWEEP_KEYS]
        # The timestamp leads so `pending_sweeps` comes back oldest first, and
        # the id follows so two sweeps opened in the same microsecond cannot
        # collide on one key.
        sk = f"{SWEEP_PREFIX}{now}#{sweep_id}#{start // SWEEP_KEYS}"
        written.append(sk)
        steps.append((
            _put(
                _lib_pk(lib), sk,
                {"sweep": sweep_id, "opened": now,
                 "blobs": [{"node": node_id, "key": key} for node_id, key in chunk]},
            ),
            None,
        ))

    for start in range(0, len(steps), TRANSACTION_ITEMS):
        _write(steps[start : start + TRANSACTION_ITEMS])
    return written


def close_sweep(lib: str, sort_keys: list[str]) -> None:
    """Drop a sweep's rows once its bytes are deleted. Point deletes, no query.

    Unconditional and tolerant of a row that is already gone: `drain` may have
    discharged the sweep first, and a delete racing its own recovery is a state
    both sides should treat as finished rather than as a conflict.
    """
    if not sort_keys:
        return
    steps = [(_delete(_lib_pk(lib), sk), None) for sk in sort_keys]
    for start in range(0, len(steps), TRANSACTION_ITEMS):
        _write(steps[start : start + TRANSACTION_ITEMS])


def pending_sweeps(lib: str) -> list[dict]:
    """Every open sweep in a library, oldest first.

    Oldest first because the sort key leads with the timestamp, and because a
    sweep that has been open longest is the one least likely to belong to a
    request still running.
    """
    return [_attributes(item) for item in _query(
        TableName=config.catalog_table(),
        KeyConditionExpression="pk = :pk AND begins_with(sk, :sk)",
        ExpressionAttributeValues={":pk": {"S": _lib_pk(lib)},
                                   ":sk": {"S": SWEEP_PREFIX}},
    )]


def live_nodes(node_ids: list[str]) -> set[str]:
    """Which of these node ids still have a `META` row.

    `records` answers the same question but reads the whole record and raises on
    a partial batch; this only needs existence, over ids that are *expected* to
    be absent. Absence is the answer here, not a failure.
    """
    if not node_ids:
        return set()

    found: set[str] = set()
    unique = sorted(set(node_ids))
    for start in range(0, len(unique), BATCH_GET_KEYS):
        chunk = unique[start : start + BATCH_GET_KEYS]
        try:
            response = dynamodb.client().batch_get_item(
                RequestItems={
                    config.catalog_table(): {
                        "Keys": [{"pk": {"S": _node_pk(node_id)}, "sk": {"S": META}}
                                 for node_id in chunk],
                        "ProjectionExpression": "pk",
                    }
                }
            )
        except ClientError as exc:
            logger.warning("BatchGetItem failed while draining sweeps: %s", exc)
            raise UpstreamError("Could not read the catalog") from exc

        for item in response.get("Responses", {}).get(config.catalog_table(), []):
            found.add(item["pk"]["S"].removeprefix("NODE#"))
        # Unprocessed keys are treated as LIVE — not retried, not assumed gone.
        # The whole point of this read is to decide whether deleting bytes is
        # safe, and "I did not manage to look" must fall on the side of keeping
        # them. The sweep stays open and the next delete asks again.
        for key in (response.get("UnprocessedKeys", {})
                    .get(config.catalog_table(), {}).get("Keys", [])):
            found.add(key["pk"]["S"].removeprefix("NODE#"))
    return found


def set_blob(
    node_id: str,
    blob_key: str,
    *,
    size: int | None = None,
    content_type: str | None = None,
    checksum: str | None = None,
) -> dict:
    """Point a file node at its bytes.

    The by-parent item is untouched, because it does not carry `blob_key`,
    `size` or `content_type` — so this is one item, and still a
    transaction. That costs twice the write capacity of a bare `UpdateItem` and
    buys one thing worth having: every write in this module fails the same way,
    through `_write`, with a per-item reason. A single `UpdateItem` here would
    be the one path with its own error handling to keep true.

    `blob_key` is stored exactly as given. It is not validated against a prefix,
    not checked for existence in the bucket, and not derived from `node_id` —
    a key is a pointer, and this module forms no second opinion about one.
    """
    if not blob_key:
        raise ValidationError("blob_key is required")

    record = node(node_id)
    if record["kind"] != KIND_FILE:
        raise ValidationError("only a file can carry a blob")

    now = _now()
    assignments = {"blob_key": blob_key, "updated_at": now}
    if size is not None:
        assignments["size"] = size
    if content_type is not None:
        assignments["content_type"] = content_type
    # The MD5 of the bytes, off the ETag of the single PUT that wrote them.
    # Optional because a caller that did not learn one — a legacy path, or a
    # multipart ETag `s3.content_hash` refused — must leave the row alone rather
    # than blank a hash somebody else recorded.
    if checksum is not None:
        assignments["checksum"] = checksum
    if checksum is not None:
        assignments["checksum"] = checksum

    _write([(_update_meta(node_id, assignments), NotFoundError(node_id))])

    logger.info("Set blob on %s", node_id)
    return {**record, **assignments}


# ═══════════════════════════════ entities ═══════════════════════════════
#
# Characters, projects, runs, scenes and movies. Everything above this line is
# the file tree; everything below is what the tree hangs off.
#
# ## Why an entity is two items
#
# The record is keyed on the **id**, because the id is what every other row
# points at and it must never change: `CHAR#<char_id>` / `META`. That answers
# "read this character" and answers nothing about "every character in this
# library" — this table must never be scanned — so a second item exists purely
# as the **list index**: `LIB#<lib>` / `CHAR#<char_id>`, one query per library.
#
# ## The second item is a listing, never a name claim
#
# A character has one free-text `name`, it is a LABEL, and nothing resolves an
# entity by it — the SPA routes on `char-<uuid>`, the API addresses ids, and an
# edge stores an id. So a duplicate name is two rows that look alike in a list,
# which a person fixes by renaming one, and it is not worth a condition
# expression, a second failure mode and a 409 the client has to handle.
#
# The index item is keyed on the id it points at, which means a rename touches
# exactly one row: the record. Nothing to keep in step, nothing to move in a
# transaction, nothing to half-happen.
#
# ## The index is a pointer, never a projection
#
# It carries the entity id and a timestamp and nothing else. Putting the `name`
# on it would put a mutable copy on a second item that every rename has to keep
# in step — the trap `GET /api/nodes` already avoids by pairing a query with a
# `BatchGetItem`, and the listing here is the same shape for the same reason.
#
# **The run listing row is the one deliberate exception**, and it is deliberate
# because a run is immutable once it completes: there is nothing left to keep in
# step, and the runs screen would otherwise need a `BatchGetItem` over hundreds
# of envelopes to draw a grid of thumbnails.
#
# ## `rev` is compare-and-swap, not check-then-write
#
# Every mutation of a record carries the `rev` the caller last read and fails the
# transaction if it moved. Re-reading `updated` and refusing if it had changed
# would be a check and a write with a gap between them; a `ConditionExpression`
# has no gap.


def entity_kind(entity_id: str) -> str:
    """Which kind an entity id names, read off its prefix.

    **The one place in this service that parses an id**, and the exception is
    forced rather than chosen: the reverse pointer a root folder carries is a
    bare `entity: "char-…"`, and a `GetItem` needs a partition. Storing the kind
    beside it would be a second copy of something the id already says, on a row
    that is written once and never revisited.

    It is a closed set of five, and an unrecognised prefix is a refusal rather
    than a guess — the alternative is composing `SOMETHING#<id>` and getting a
    404 that names nothing.
    """
    prefix = entity_id.split("-", 1)[0] if entity_id else ""
    if prefix not in _KIND_BY_ID_PREFIX:
        raise ValidationError(f"'{entity_id}' does not name an entity")
    return _KIND_BY_ID_PREFIX[prefix]


def _entity_pk(kind: str, entity_id: str) -> str:
    return f"{ENTITY_KEYS[kind][1]}{entity_id}"


def _mint(kind: str) -> str:
    return f"{ENTITY_KEYS[kind][0]}-{uuid.uuid4()}"


def _member_sk(kind: str, entity_id: str) -> str:
    """Where a library records that it holds this entity.

    Deliberately the same string as the entity's own partition key: the row says
    "this library holds `CHAR#<id>`", and spelling it any other way would be a
    second encoding of the same fact to get wrong.
    """
    return _entity_pk(kind, entity_id)


#: Turn every `Decimal` a read hands back into an int or a float — `jsonify`
#: refuses one outright, and `_record` does this for `size` alone because a node
#: has exactly one number on it while an entity record has `rev`, three `counts`,
#: a reference `order` and a `cost.amount` nested two deep.
#:
#: **It is `digest.plain_numbers` and not a function of this module's own**,
#: because the fingerprint needs the identical walk for a different reason: a
#: value hashed before the round trip and rehashed after it must produce one
#: hash. Two implementations of that walk is two ways for a payload to hash
#: twice.
_numbers = digest.plain_numbers


def _entity(item: dict) -> dict:
    """Unmarshal one entity item, keys dropped and numbers made plain."""
    record = _attributes(item)
    record.pop("pk", None)
    record.pop("sk", None)
    return _numbers(record)


# ──────────────────────────── entity reads ────────────────────────────


def entity(kind: str, entity_id: str) -> dict:
    """One entity's record, by id.

    The `kind` is passed rather than derived so a caller cannot ask
    `GET /api/characters/<a project id>` and be answered. That is a 404 naming
    the id, which is what a client that followed a stale link deserves — and it
    is checked here rather than in six route modules.
    """
    if kind not in ENTITY_KEYS:
        raise ValidationError(f"'{kind}' is not an entity kind")
    if entity_kind(entity_id) != kind:
        raise NotFoundError(entity_id)

    try:
        response = dynamodb.client().get_item(
            TableName=config.catalog_table(),
            Key={"pk": {"S": _entity_pk(kind, entity_id)}, "sk": {"S": META}},
        )
    except ClientError as exc:
        logger.warning("GetItem failed for %s: %s", entity_id, exc)
        raise UpstreamError("Could not read the catalog") from exc

    item = response.get("Item")
    if not item:
        raise NotFoundError(entity_id)
    return _entity(item)


def entity_summary(entity_id: str) -> dict:
    """`{kind, id, name}` for one entity — what a node's `owner` reports.

    Deliberately three fields. A listing that drew the whole record per file
    would fetch a profile per thumbnail, and the SPA needs exactly enough to
    write "in <name>" and link it.
    """
    kind = entity_kind(entity_id)
    record = entity(kind, entity_id)
    return {"kind": kind, "id": record["id"], "name": record.get("name")}


def _members(lib: str, kind: str) -> list[dict]:
    items = _query(
        TableName=config.catalog_table(),
        KeyConditionExpression="pk = :pk AND begins_with(sk, :member)",
        ExpressionAttributeValues={
            ":pk": {"S": _lib_pk(lib)},
            ":member": {"S": ENTITY_KEYS[kind][1]},
        },
    )
    return [_entity(item) for item in items]


def entities_by_id(kind: str, entity_ids: list[str]) -> dict[str, dict]:
    """Full records for many entities at once, keyed by id.

    Public because the reverse-link routes all end the same way: `by-sk` hands
    back a list of ids and the caller needs the records behind them.

    `records` for nodes, one partition prefix over. Kept separate rather than
    generalised because the two differ in the one thing that matters — which
    partition a key is built in — and a shared helper taking a prefix would be a
    place to pass the wrong one.
    """
    wanted = list(dict.fromkeys(entity_ids))
    found: dict[str, dict] = {}
    for start in range(0, len(wanted), BATCH_GET_KEYS):
        batch = wanted[start : start + BATCH_GET_KEYS]
        batch_keys = [
            {"pk": {"S": _entity_pk(kind, entity_id)}, "sk": {"S": META}}
            for entity_id in batch
        ]
        for item in _batch_get(batch_keys):
            record = _entity(item)
            found[record["id"]] = record
    return found


def entities_in(lib: str, kind: str) -> list[dict]:
    """Every character, or every project, in one library.

    **One query plus a batched read** — the index rows say which ids exist and
    `BatchGetItem` fetches the records. The same shape `GET /api/nodes` uses, for
    the same reason: the index stays a pointer rather than a projection somebody
    has to keep in step.

    An index row naming a record that is not there is logged and dropped rather
    than raised. Every create and delete here is one transaction over both items,
    so one without the other means a row was written by hand — and a listing that
    500s over it is a library nobody can open.

    **There is no `entity_by_name`**: a name is a label, so resolving one would
    have to pick between duplicates. Every caller addresses an id.
    """
    members = _members(lib, kind)
    found = entities_by_id(kind, [member["entity"] for member in members])

    listed = []
    for member in members:
        record = found.get(member["entity"])
        if record is None:
            logger.warning("Library %s lists a missing %s: %s", lib, kind, member["entity"])
            continue
        listed.append(record)
    return listed


def linked(entity_id: str, holder_kind: str) -> list[str]:
    """Everything of one kind that points at this entity, read backwards.

    `by-sk` inverts the table, so `sk = CHAR#<id> AND begins_with(pk, "PROJ#")`
    is "which projects involve this character" and the same query one prefix over
    is "which runs used it".
    """
    prefix = ENTITY_KEYS[holder_kind][1]
    items = _query(
        TableName=config.catalog_table(),
        IndexName=BY_SK_INDEX,
        KeyConditionExpression="sk = :sk AND begins_with(pk, :holder)",
        ExpressionAttributeValues={
            ":sk": {"S": f"{ENTITY_KEYS[entity_kind(entity_id)][1]}{entity_id}"},
            ":holder": {"S": prefix},
        },
    )
    return [_attributes(item)["pk"][len(prefix) :] for item in items]


def links(entity_id: str, target_kind: str) -> list[str]:
    """Everything of one kind this entity points at, read forwards."""
    kind = entity_kind(entity_id)
    prefix = ENTITY_KEYS[target_kind][1]
    items = _query(
        TableName=config.catalog_table(),
        KeyConditionExpression="pk = :pk AND begins_with(sk, :target)",
        ExpressionAttributeValues={
            ":pk": {"S": _entity_pk(kind, entity_id)},
            ":target": {"S": prefix},
        },
    )
    return [_attributes(item)["sk"][len(prefix) :] for item in items]


# ──────────────────────────────── edges ────────────────────────────────
#
# **An edge is a row whose sort key is the TARGET's id**: `pk = <A>#<a_id>`,
# `sk = <B>#<b_id>`. That shape is the only one `by-sk` can invert — in that
# index `sk` is the hash key, and a hash key takes an exact value and never a
# prefix — so every relationship that has to be readable backwards is spelled
# this way and no other. `links()` reads one forwards, `linked()` backwards.
#
# It is deliberately not the only row shape here, and the other two are not
# defects:
#
# | Shape | Sort key | What it is for |
# |---|---|---|
# | **edge** | `<B>#<b_id>` | set membership, readable from both ends |
# | **listing** | `<KIND>#<created>#<id>` | chronological pagination — `project_entities` |
# | **ordered child** | `SHOT#<n>` | a positional entity carrying payload |
#
# A listing row embeds a timestamp so a project's runs paginate newest-first,
# which costs it a reverse query it does not need — a run records its `project`
# on its own record. An ordered child is an entity in its own right: a shot
# exists before anything has been rendered into it, so its identity is its
# position and not the run it may later bind.
#
# **Where an ordered child points at an entity, it gets an edge row beside it**,
# written in the SAME transaction — for the reason `create_project_entity`
# already gives about character usage: a link written afterwards is a link a
# crash can lose. That is the whole rule: a movie's scenes are also a JSON list
# and a scene's shots also name their run in an attribute, and no index can see
# into either — the edge row beside each is what makes "which movie cuts this
# scene" and "which scene used this run" one `by-sk` query apiece.


def edge_sk(target_id: str) -> str:
    """`CHAR#<id>` — the sort key an edge to this entity is filed under."""
    return f"{ENTITY_KEYS[entity_kind(target_id)][1]}{target_id}"


def edge_steps(
    source_kind: str,
    source_id: str,
    lib: str,
    targets: list[str],
    current: list[str] | set[str],
    now: str | None = None,
) -> list[tuple[dict, Exception | None]]:
    """Transaction steps that make this entity's edge set exactly `targets`.

    Returned rather than written, so an edge can land in the same transaction as
    whatever it describes. `set_edges` is the standalone caller.

    Duplicates in `targets` collapse: an edge is set membership. An ordered
    collection that allows the same target twice — a movie may cut one scene
    twice as a reprise — keeps its order and its duplicates in its own list or
    rows, and the edge rows beside it are the deduplicated set.
    """
    now = now or _now()
    pk = _entity_pk(source_kind, source_id)
    wanted = list(dict.fromkeys(targets))

    steps = [
        (_put(pk, edge_sk(target), {"lib": lib, "created": now}), None)
        for target in wanted
    ]
    steps += [
        (_delete(pk, edge_sk(target)), None)
        for target in set(current) - set(wanted)
    ]
    return steps


def set_edges(source_kind: str, source_id: str, lib: str,
              target_kind: str, targets: list[str]) -> list[str]:
    """Replace this entity's edges of one kind, and answer with the set written.

    A replace rather than an add: the SPA edits a set and the CLI reads the set
    first, so an add-only endpoint would need a remove beside it and a client
    that got the difference wrong would accumulate links nothing removes.
    """
    current = links(source_id, target_kind)
    steps = edge_steps(source_kind, source_id, lib, targets, current)
    for start in range(0, len(steps), TRANSACTION_ITEMS):
        _write(steps[start : start + TRANSACTION_ITEMS])
    return list(dict.fromkeys(targets))


# ──────────────────────────── entity writes ────────────────────────────


def _put(pk: str, sk: str, attributes: dict, *, unique: bool = False) -> dict:
    item = {
        "TableName": config.catalog_table(),
        "Item": _item({"pk": pk, "sk": sk, **attributes}),
    }
    if unique:
        item["ConditionExpression"] = "attribute_not_exists(pk)"
    return {"Put": item}


def _delete(pk: str, sk: str) -> dict:
    return {"Delete": {"TableName": config.catalog_table(), "Key": {"pk": {"S": pk}, "sk": {"S": sk}}}}


def _revised(kind: str, entity_id: str, assignments: dict, rev: int) -> dict:
    """Update an entity record only if its `rev` is still the one that was read.

    Compare-and-swap in one operation. `rev` appears twice in the expression —
    once as the attribute being incremented and once in the condition — under two
    aliases for the same name, which DynamoDB allows and which keeps the
    assignment arithmetic identical to every other update here.
    """
    names = {f"#a{index}": attribute for index, attribute in enumerate(assignments)}
    values = {
        f":a{index}": _serialize(value)
        for index, value in enumerate(assignments.values())
        if value is not None
    }
    sets = [f"{alias} = :a{alias[2:]}" for alias in names if f":a{alias[2:]}" in values]
    removes = [alias for alias in names if f":a{alias[2:]}" not in values]

    clauses = []
    if sets:
        clauses.append("SET " + ", ".join(sets))
    if removes:
        clauses.append("REMOVE " + ", ".join(removes))

    names["#rev"] = "rev"
    values[":rev"] = {"N": str(rev)}
    return {
        "Update": {
            "TableName": config.catalog_table(),
            "Key": {"pk": {"S": _entity_pk(kind, entity_id)}, "sk": {"S": META}},
            "UpdateExpression": " ".join(clauses),
            "ExpressionAttributeNames": names,
            "ExpressionAttributeValues": values,
            "ConditionExpression": "attribute_exists(pk) AND #rev = :rev",
        }
    }


def _stale(kind: str, rev: int) -> ConflictError:
    return ConflictError(
        f"the {kind} was changed by someone else; re-read and retry "
        f"(rev {rev} → {rev + 1})"
    )


def _bump_counts(project_id: str, field: str, delta: int) -> dict:
    """Move one of a project's three counters inside somebody else's transaction.

    Maintained rather than scanned, which is the whole reason it is a step here
    and not a query on the read path: "how many runs does this project have" is a
    number on the record, and a screen that had to count them would page through
    every listing row to draw a card.
    """
    return {
        "Update": {
            "TableName": config.catalog_table(),
            "Key": {"pk": {"S": _entity_pk(ENTITY_PROJECT, project_id)}, "sk": {"S": META}},
            "UpdateExpression": "SET #counts.#field = #counts.#field + :delta",
            "ExpressionAttributeNames": {"#counts": "counts", "#field": field},
            "ExpressionAttributeValues": {":delta": {"N": str(delta)}},
            "ConditionExpression": "attribute_exists(pk)",
        }
    }


def _tree_steps(parent: dict, entity_id: str, layout: tuple) -> tuple[dict, list]:
    """The root folder an entity owns, plus its starting layout, as one write.

    Returns the root record and the steps that create it and its children. The
    root carries `entity` — one attribute, written once, never changed — and it
    is what lets a listing draw a character card instead of a folder icon and
    what `GET /api/nodes/<id>/owner` walks up to. The forward pointer is `root`
    on the record. One field in each direction, and no map of folder names in
    either.

    **The folder is NAMED by the entity id, not by the display name.** A folder's
    name is unique among its siblings — genuinely, because `child_by_name`
    resolves a path segment — so naming entity roots by their display name would
    refuse the second character called `Anna` from the tree, a uniqueness the
    entity model deliberately does not impose on names.

    So the id is the folder's name here, the way it is already the S3 key's, and
    the display name lives on the record alone. A listing hands back `owner` for
    an entity root, which is where a client gets a name to draw.
    """
    root = _new_node(parent, entity_id, KIND_FOLDER, entity=entity_id)
    steps = _node_steps(root)
    for name in layout:
        steps += _node_steps(_new_node(root, name, KIND_FOLDER))
    return root, steps


def create_character(
    lib: str,
    parent_id: str,
    *,
    name: str,
    profile: dict,
    layout: tuple,
) -> dict:
    """A character, its library index row, its root folder and its pools — one write.

    **Twelve items in one `TransactWriteItems`**: the record, the index row, and
    two each for the root and the four starting pools. Either all of it exists or
    none of it does, which is the property that makes "creating a character"
    something a person can retry after a timeout without inspecting what
    survived.

    **The four pools are a starting layout, not a schema.** They exist because an
    empty character is unhelpful; nothing afterwards requires them. Rename
    `reference/`, delete `archive/`, add one of your own — all ordinary file
    operations, and none of them breaks anything, because an image is identity
    when it carries the `default` tag and not because of the folder it sits in.

    **Nothing here can collide.** A name is a free-text label and the root
    folder is named by the id, so both keys are minted UUIDs and the only
    conflict left is one that cannot happen.
    """
    parent = _folder_node(parent_id)
    if parent["lib"] != lib:
        raise ValidationError("a character is created in its own library")

    char_id = _mint(ENTITY_CHARACTER)
    now = _now()
    root, tree = _tree_steps(parent, char_id, layout)

    record = {
        "id": char_id,
        "lib": lib,
        "name": name,
        "rev": 1,
        "created": now,
        "updated": now,
        "root": root["node_id"],
        "hero": None,
        "profile": profile,
    }

    _write(
        [
            (
                _put(_lib_pk(lib), _member_sk(ENTITY_CHARACTER, char_id),
                     {"entity": char_id, "created": now}),
                None,
            ),
            (_put(_entity_pk(ENTITY_CHARACTER, char_id), META, record), None),
            *tree,
        ]
    )

    logger.info("Created character %s in %s", char_id, lib)
    return record


def create_project(
    lib: str,
    parent_id: str,
    *,
    name: str,
    description: str | None,
    characters: list[str],
    layout: tuple,
) -> dict:
    """A project, its index row, its root, its five subfolders and its involvements.

    `characters` are written as `PROJ#<id>` / `CHAR#<id>` rows rather than as a
    list on the record, which is what makes the reverse question answerable: read
    forwards it is "who is in this project", and read backwards on `by-sk` it is
    "which projects involve this character" — which a list on the record could
    not answer.
    """
    parent = _folder_node(parent_id)
    if parent["lib"] != lib:
        raise ValidationError("a project is created in its own library")

    proj_id = _mint(ENTITY_PROJECT)
    now = _now()
    root, tree = _tree_steps(parent, proj_id, layout)

    record = {
        "id": proj_id,
        "lib": lib,
        "name": name,
        "description": description or "",
        "rev": 1,
        "created": now,
        "updated": now,
        "root": root["node_id"],
        "hero": None,
        "counts": {"runs": 0, "scenes": 0, "movies": 0},
    }

    _write(
        [
            (
                _put(_lib_pk(lib), _member_sk(ENTITY_PROJECT, proj_id),
                     {"entity": proj_id, "created": now}),
                None,
            ),
            (_put(_entity_pk(ENTITY_PROJECT, proj_id), META, record), None),
            *tree,
            *[
                (
                    _put(_entity_pk(ENTITY_PROJECT, proj_id),
                         f"{ENTITY_KEYS[ENTITY_CHARACTER][1]}{char_id}",
                         {"lib": lib, "created": now}),
                    None,
                )
                for char_id in characters
            ],
        ]
    )

    logger.info("Created project %s in %s", proj_id, lib)
    return record


def update_entity(kind: str, record: dict, rev: int, assignments: dict) -> dict:
    """Change an entity's attributes under one `rev`.

    **A stale `rev` is a 409 and never a silent overwrite.** Two people editing
    one profile is the case this exists for: the second save is refused with the
    numbers in the message, and the client re-reads rather than losing the
    first's work.

    **A rename is an assignment like any other**: the name is a label on this
    row, the index row is keyed on the id, and the root folder is named by the
    id. One item changes.
    """
    now = _now()
    assignments = {**assignments, "rev": rev + 1, "updated": now}
    _write([(_revised(kind, record["id"], assignments, rev), _stale(kind, rev))])
    return {**record, **{k: v for k, v in assignments.items() if v is not None}}


def _entity_rows(kind: str, entity_id: str) -> list[dict]:
    """Every row in one entity's own partition, records and links alike."""
    return _query(
        TableName=config.catalog_table(),
        KeyConditionExpression="pk = :pk",
        ExpressionAttributeValues={":pk": {"S": _entity_pk(kind, entity_id)}},
    )


def delete_project_cascade(record: dict, *, delete_files: bool) -> dict:
    """A project and everything it holds. **Movies, then scenes, then runs.**

    **THIS CANNOT BE ONE TRANSACTION AND MUST NOT PRETEND TO BE.** A project of
    29 runs is ~377 items — 87 entity rows plus two per node — and
    `TRANSACTION_ITEMS` caps a `TransactWriteItems` at 100. So this is a
    sequence, and the ORDER is what makes an interruption survivable: every
    child is deleted before the project that lists it, exactly as `delete_node`
    deletes a subtree deepest-first. What a crash leaves is a project holding
    fewer children — visible, and finished by running this again.

    The kind order matters for the same reason one level down: a movie names
    scenes and a scene names runs, so taking them in that order never leaves a
    record pointing at something already deleted.

    Deleting the project alone would leave every run's envelope naming a project
    id that does not exist — the one state the model cannot repair from — which
    is why there is no shortcut past the cascade.
    """
    blob_keys: list[str] = []
    sweeps: list[str] = []
    removed = collections.Counter()
    for kind in (ENTITY_MOVIE, ENTITY_SCENE, ENTITY_RUN):
        for row in project_entities(record["id"], kind):
            child = entity(kind, row["id"])
            result = delete_entity(kind, child, delete_files=delete_files)
            blob_keys.extend(result["blob_keys"])
            sweeps.extend(result["sweeps"])
            removed[kind] += 1
    result = delete_entity(ENTITY_PROJECT, record, delete_files=delete_files)
    blob_keys.extend(result["blob_keys"])
    sweeps.extend(result["sweeps"])
    logger.info("Cascade-deleted project %s (%s)", record["id"], dict(removed))
    return {"id": record["id"], "lib": record["lib"], "blob_keys": blob_keys,
            "sweeps": sweeps, "removed": dict(removed)}


def delete_entity(kind: str, record: dict, *, delete_files: bool) -> dict:
    """Remove an entity, its claim, its links and — if asked — its folder.

    **Files are kept by default and the folder is orphaned into the library
    root.** The reverse default loses media to a typo, and there is no undo for
    an S3 delete this service can perform. `?files=delete` is the explicit
    request, and it is the only path that passes `allow_entities` to
    `delete_node`.

    **The record goes before the tree, and that order is the recoverable one.**
    What survives an interruption is a folder nothing claims — visible, movable,
    deletable by hand — rather than a record naming a node that does not exist, which is
    the one broken state the tree cannot repair.

    Everything that *points at* this entity is the caller's problem and is
    checked there: `DELETE /api/characters/<id>` refuses while a project or a run
    still links it. Here the links deleted are the ones this entity's own
    partition holds.
    """
    rows = _entity_rows(kind, record["id"])
    steps: list[tuple[dict, Exception | None]] = [
        (_delete(_attributes(row)["pk"], _attributes(row)["sk"]), None) for row in rows
    ]
    if kind in LISTED_KINDS:
        steps.append(
            (_delete(_lib_pk(record["lib"]), _member_sk(kind, record["id"])), None))
    for holder in (ENTITY_PROJECT, ENTITY_RUN):
        for holder_id in linked(record["id"], holder):
            steps.append(
                (
                    _delete(
                        _entity_pk(holder, holder_id),
                        f"{ENTITY_KEYS[kind][1]}{record['id']}",
                    ),
                    None,
                )
            )
    if kind in COUNT_FIELD and record.get("project"):
        # **Decrement only what was counted.** A run is created as a draft and
        # deliberately not counted until it is submitted, so a draft that is
        # discarded and deleted would otherwise take the project's run count
        # below zero and keep it there — a number no later submission can
        # correct, on a card a person reads. `counted` is written by the
        # transition into `pending`; a scene and a movie carry no such flag and
        # are always counted, which is why the default is True.
        if record.get("counted", True):
            steps.append((_bump_counts(record["project"], COUNT_FIELD[kind], -1), None))
        steps.append(
            (
                _delete(
                    _entity_pk(ENTITY_PROJECT, record["project"]),
                    f"{ENTITY_KEYS[kind][1]}{record['created']}#{record['id']}",
                ),
                None,
            )
        )

    for start in range(0, len(steps), TRANSACTION_ITEMS):
        _write(steps[start : start + TRANSACTION_ITEMS])

    root_id = record.get("root") or record.get("folder")
    blob_keys: list[str] = []
    sweeps: list[str] = []
    if root_id:
        if delete_files:
            freed = delete_node(root_id, allow_entities=True)
            blob_keys = freed["blob_keys"]
            sweeps = list(freed["sweep"])
        else:
            _orphan(root_id, record["lib"])

    logger.info("Deleted %s %s (files %s)", kind, record["id"],
                "deleted" if delete_files else "kept")
    return {"id": record["id"], "lib": record["lib"],
            "blob_keys": blob_keys, "sweeps": sweeps}


def _orphan(node_id: str, lib: str) -> None:
    """Cut a folder loose from the entity that owned it.

    The reverse pointer goes first, because a folder still carrying `entity`
    after its record is deleted is what `delete_node` refuses and what `owner_of`
    logs about. Then it is moved to the library root, where it is an ordinary
    folder somebody can browse, rename or delete by hand.

    A name already taken there is not an error worth failing the delete over —
    the entity is already gone — so it takes the next number, the same form
    `catalog.create_numbered` and `manage.copy_objects` produce.
    """
    record = node(node_id)
    _write([(_update_meta(node_id, {"entity": None}), NotFoundError(node_id))])

    root_id = library(lib)["root_node"]
    if record["parent_id"] == root_id:
        return
    for attempt in range(1, keys.MAX_NAME_VARIANTS + 1):
        try:
            move_node(node_id, root_id)
            return
        except ConflictError:
            rename_node(node_id, keys.numbered_name(record["name"], attempt + 1))

    logger.warning("Could not orphan %s into the library root", node_id)


# ─────────────────────────── reference entries ───────────────────────────
#
# **There are no reference rows.** Which of a character's pictures are its
# identity, and what each picture shows, are tags on the node — `default` for
# the handful a generation is shown, `face` or `body` for what the picture is —
# so this module stores nothing about it and `services/browse.entries` answers
# the question with a tag filter over the character's branch.
#
# A tag cannot drift from the file it is written on. A list of node ids on the
# record would have to name live rows, and nothing could keep it doing so.
# `describe_node` above is the whole of the write path.


def set_project_characters(project_id: str, lib: str, characters: list[str]) -> list[str]:
    """Replace a project's involvement links. One caller of `set_edges`."""
    return set_edges(ENTITY_PROJECT, project_id, lib, ENTITY_CHARACTER, characters)


# ──────────────────── runs, scenes and movies ────────────────────
#
# The three kinds a project holds. All of them are an **envelope**: the fields
# studio owns, validates and queries, beside a payload it stores and never
# decodes.
#
# | Studio owns (row, validated, queryable) | The provider owns (blob, verbatim) |
# |---|---|
# | id, project, status, model, engine, kind, characters, bindings (node ids), timings, prediction id, error, outputs | the exact `input` sent, the exact response returned |
#
# The pipeline changes the payload's shape freely, so a service that parsed one
# would become a liar; the envelope is what gives the app a run it can render.
#
# **The listing row is a projection and the only one in this module.** A project's
# runs are `pk = PROJ#<id>, begins_with(sk, "RUN#"), ScanIndexForward=false` —
# real pagination, newest first — and the row carries status, model, kind and a
# thumbnail so the grid draws without a `BatchGetItem` over hundreds of
# envelopes. It is safe to project *because a run is immutable once it
# completes*: there is nothing left to keep in step. Do not copy this reasoning
# onto a record a person edits, where the opposite is true.


def _listing_sk(kind: str, created: str, entity_id: str) -> str:
    """`RUN#<created>#<run_id>` — sortable, unique, and newest-last by string.

    The timestamp comes first so the range is chronological, and the id follows
    so two entities created in the same microsecond are still two rows. The
    reverse order a listing wants is `ScanIndexForward=False` rather than a
    reversed key, because the same rows are also read oldest-first by anything
    replaying a project.
    """
    return f"{ENTITY_KEYS[kind][1]}{created}#{entity_id}"


def _edge_targets(attributes: dict) -> list[str]:
    """Every entity id an envelope points at, flattened for `edge_steps`.

    `characters` and `scenes` are lists of ids, and each is an edge like any
    other — "which runs used this character" is the same question as "which
    projects involve this character", asked one prefix over.
    """
    return [*(attributes.get("characters") or []), *(attributes.get("scenes") or [])]


def create_project_entity(
    kind: str,
    lib: str,
    project_id: str,
    parent_id: str,
    *,
    attributes: dict,
    listing: dict,
    subfolders: tuple = (),
    count: bool = True,
) -> dict:
    """A run, a scene or a movie: envelope, listing row, folder — one write.

    **Its folder is named for its id and its record names the folder's node
    id**, which is why renaming or moving that folder afterwards strands nothing:
    no record anywhere holds a path. A scene and a movie carry a free-text `name`
    on the record and their folder is still named by the id, because a folder
    name is unique among its siblings and naming these by a label would refuse
    the second scene called `Opening` from the tree.

    **`count=False` creates the entity without counting it, and a RUN uses it.**
    A run is created as a `draft` — when it is planned, not when it is
    submitted — so counting at creation would make a project's run count include
    intentions nobody bought. The count is bumped instead by the transition into
    `pending`, through `update_project_entity(bump_count=True)`, which is the
    moment the run stops being a plan. A scene and a movie still count at
    creation: both exist the moment they are planned and neither costs anything.

    **Every edge this entity carries goes in the same transaction**, because
    "which runs used this character" has to be true the moment the run exists —
    a link written afterwards is a link a crash can lose. `_edge_targets` is
    the whole list, and `edge_sk` reads each target's kind off its own id.
    """
    parent = _folder_node(parent_id)
    entity_id = _mint(kind)
    now = _now()

    folder = _new_node(parent, entity_id, KIND_FOLDER, entity=entity_id)
    steps = _node_steps(folder)
    for name in subfolders:
        steps += _node_steps(_new_node(folder, name, KIND_FOLDER))

    record = {
        "id": entity_id,
        "lib": lib,
        "project": project_id,
        "rev": 1,
        "created": now,
        "updated": now,
        "folder": folder["node_id"],
        **attributes,
    }

    steps = [
        (
            _put(_entity_pk(kind, entity_id), META, record, unique=True),
            ConflictError(f"{entity_id} already exists"),
        ),
        (
            _put(_entity_pk(ENTITY_PROJECT, project_id), _listing_sk(kind, now, entity_id),
                 {"lib": lib, "id": entity_id, "created": now, **listing}),
            None,
        ),
        *([(_bump_counts(project_id, COUNT_FIELD[kind], 1), NotFoundError(project_id))]
          if count else []),
        *steps,
        *edge_steps(kind, entity_id, lib, _edge_targets(attributes), [], now),
    ]

    _write(steps)
    logger.info("Created %s %s in project %s", kind, entity_id, project_id)
    return record


def project_entities(project_id: str, kind: str) -> list[dict]:
    """One project's runs, scenes or movies as listing rows, newest first.

    Rows rather than records, deliberately: this is what draws the grid, and
    fetching the envelopes would be the `BatchGetItem` the projection exists to
    avoid. `GET /api/runs/<id>` is where the envelope lives.
    """
    items = _query(
        TableName=config.catalog_table(),
        KeyConditionExpression="pk = :pk AND begins_with(sk, :kind)",
        ExpressionAttributeValues={
            ":pk": {"S": _entity_pk(ENTITY_PROJECT, project_id)},
            ":kind": {"S": ENTITY_KEYS[kind][1]},
        },
        ScanIndexForward=False,
    )
    return [{**_entity(item), "project": project_id} for item in items]


def update_project_entity(
    kind: str, record: dict, assignments: dict, listing: dict | None = None,
    edges: dict[str, list[str]] | None = None, bump_count: bool = False,
) -> dict:
    """Move a run, scene or movie forward. **No `rev`, and that is deliberate.**

    A character or a project is edited by a person, twice at once, and losing
    somebody's paragraph is the failure `rev` exists to prevent. A run is written
    by the machine that submitted it, in a fixed sequence — pending, submitted,
    succeeded — and the only concurrent writer is a second attempt at the same
    transition. Demanding a `rev` there would make the CLI re-read a record to
    report that a prediction finished.

    The listing row is updated in the same transaction when its projection
    changes, so a grid never shows `pending` for a run whose envelope says
    `succeeded`.

    `bump_count` adds one to the project's count for this kind, in the same
    transaction. It exists for the run that has just been submitted: a run is
    created as a draft and deliberately not counted, so something has to count it
    when it stops being one. The caller decides, because only the caller knows
    whether this particular transition is the first one out of `draft` — see
    `routes/runs.py`, which also writes `counted` so a re-submitted run cannot be
    counted twice.

    `edges` replaces the edge rows of one or more target kinds, in that same
    transaction — `{ENTITY_SCENE: [...]}`. Scoped per kind because a replace has
    to know what it is replacing: writing a movie's scenes must not disturb the
    characters it involves. The attribute and its edge rows land together or not
    at all, which is the only reason the list and the rows cannot disagree.
    """
    now = _now()
    assignments = {**assignments, "updated": now}
    steps = [
        (
            _update({"pk": {"S": _entity_pk(kind, record["id"])}, "sk": {"S": META}}, assignments),
            NotFoundError(record["id"]),
        )
    ]
    if listing:
        steps.append(
            (
                _update(
                    {
                        "pk": {"S": _entity_pk(ENTITY_PROJECT, record["project"])},
                        "sk": {"S": _listing_sk(kind, record["created"], record["id"])},
                    },
                    listing,
                ),
                NotFoundError(record["id"]),
            )
        )
    for target_kind, targets in (edges or {}).items():
        steps += edge_steps(kind, record["id"], record["lib"], targets,
                            links(record["id"], target_kind), now)
    if bump_count:
        steps.append((_bump_counts(record["project"], COUNT_FIELD[kind], 1),
                      NotFoundError(record["project"])))

    _write(steps)
    # **A `None` assignment is reported as a `None`, because that is what was
    # written.** `_update` turns one into a REMOVE, so the row genuinely loses
    # the attribute; filtering it out of the reply would hand the caller back
    # the value it had just cleared — a write that cleared a run's `error`
    # would still show one.
    #
    # `update_entity` above still filters. It is left alone deliberately: it
    # serves characters and projects, whose `PATCH` bodies omit what they do not
    # mean to change, so a `None` there has never been a caller asking to clear.
    return {**record, **assignments}


def runs_for_character(char_id: str) -> list[dict]:
    """Every run that used one character, as envelopes.

    One `by-sk` query for the ids, one batched read for the records.
    """
    run_ids = linked(char_id, ENTITY_RUN)
    found = entities_by_id(ENTITY_RUN, run_ids)
    return sorted(found.values(), key=lambda record: record.get("created") or "", reverse=True)


# ───────────────────────────── shots ─────────────────────────────


SHOT_PREFIX = "SHOT#"


def shots(scene_id: str) -> list[dict]:
    """One scene's planned shots, in `order`."""
    items = _query(
        TableName=config.catalog_table(),
        KeyConditionExpression="pk = :pk AND begins_with(sk, :shot)",
        ExpressionAttributeValues={
            ":pk": {"S": _entity_pk(ENTITY_SCENE, scene_id)},
            ":shot": {"S": SHOT_PREFIX},
        },
    )
    entries = []
    for item in items:
        entry = _entity(item)
        entry["id"] = _deserialize(item["sk"])[len(SHOT_PREFIX) :]
        entries.append(entry)
    entries.sort(key=lambda entry: entry.get("order") or 0)
    return entries


# Everything a shot row holds, and it is the list of what a storyboard IS. A
# field the CLI authors and this tuple omits is dropped silently on the way in,
# so the tuple has to be the whole list.
#
# `panels` is a list of objects and `motion` is an object; both survive the trip
# because `_serialize` marshals nested values and `_numbers` walks them back.
#
# The two halves are worth keeping distinct in your head even though the merge
# treats them alike — authored: `order`, `beat`, `prompt`, `panels`, `motion`,
# `continues`, `status`; recorded by a render: `run`, `runref`, `node`,
# `shot_node`, `panel`, `duration`, `rendered`, `opens_on`.
SHOT_FIELDS = (
    "order", "beat", "prompt", "panels", "motion", "continues", "status",
    "opens_on", "run", "runref", "node", "shot_node", "panel", "duration", "rendered",
    # The runs this shot has been rendered by before the current one. Written by
    # `storyboard.keep_take` on the two routes below rather than by any caller —
    # a client that had to remember to preserve its own history would forget,
    # and the CLI is not the only client.
    "takes",
)


def _shot_item(scene_id: str, shot_id: str, entry: dict) -> dict:
    return _put(
        _entity_pk(ENTITY_SCENE, scene_id),
        f"{SHOT_PREFIX}{shot_id}",
        {
            **{field: entry.get(field) for field in SHOT_FIELDS},
            "created": entry.get("created") or _now(),
        },
    )


def _shot_run_edges(scene_id: str, lib: str, written: list[dict],
                    now: str) -> list[tuple[dict, Exception | None]]:
    """Edge rows making `SCENE#<id> / RUN#<id>` exactly the runs its shots bind.

    A shot's identity is its position — it exists as a plan before anything is
    rendered — so `SHOT#<n>` is the right key for it and the run it later binds
    is a field. Without an edge the run would be reachable only by reading every
    shot of every scene.

    So the edge lives beside the shot rather than replacing it, and is derived
    from the shots on every write instead of being maintained incrementally:
    a shot can gain, change or lose its run through two different routes, and a
    derived set cannot drift from the thing it is derived from.

    **A shot names a run in three places, not one.** In a boarded scene
    `shot["run"]` — the motion render — is typically empty while every *panel*
    carries a run, because boarding records the still per panel. Reading
    `shot["run"]` alone leaves the backlink empty for every boarded scene.

    | Field | What named the run |
    |---|---|
    | `shot["run"]` | the motion render for the whole shot |
    | `panels[n]["run"]` | the still boarded into panel n |
    | `opens_on["from_run"]` | the run whose last frame this shot continues from |

    All three are "this scene used that run", which is the question being
    answered. Duplicates collapse — an edge is set membership.
    """
    bound = []
    for shot in written:
        if shot.get("run"):
            bound.append(shot["run"])
        for panel in shot.get("panels") or []:
            if isinstance(panel, dict) and panel.get("run"):
                bound.append(panel["run"])
        opens_on = shot.get("opens_on")
        if isinstance(opens_on, dict) and opens_on.get("from_run"):
            bound.append(opens_on["from_run"])
    return edge_steps(ENTITY_SCENE, scene_id, lib, bound,
                      links(scene_id, ENTITY_RUN), now)


def put_shots(scene_id: str, lib: str, entries: list[dict]) -> list[dict]:
    """Revise a scene's plan **onto** the work already rendered, not over it.

    A plan revision is a person rewriting prompts. `run`, `node` and `panel` are
    what a render put there, and a plain replace would throw them away — so a
    shot matched by id keeps every field the request does not name. Shots the
    revision drops are deleted; new ones are appended.

    That rule is `entry.get(field, previous.get(field))` and it is per-field
    rather than per-half on purpose: `--force` re-ingest sends a plan the CLI has
    already merged, and a route that guessed which half a field belonged to would
    disagree with it. Naming a field wins; not naming one keeps what was there.
    """
    existing = {entry["id"]: entry for entry in shots(scene_id)}
    now = _now()

    written = []
    steps = []
    for index, entry in enumerate(entries):
        shot_id = entry.get("id") or f"shot-{uuid.uuid4()}"
        previous = existing.pop(shot_id, {})
        merged = {field: entry.get(field, previous.get(field)) for field in SHOT_FIELDS}
        # **One level deeper, for panels only.** The rule above protects a shot's
        # fields; a `panels` list that IS named replaces the stored one whole, so
        # the images and boarded flags inside it need carrying across too.
        deeper = storyboard.merge_panels(previous, entry)
        if deeper is not None:
            merged["panels"] = deeper
        # **The STORE guarantees the shape; the write does not overwrite it.**
        # `opens_on` is recorded by `scenes handoff` and must survive a revision
        # that does not mention it — so it is never sent — but a shot that has
        # never had one still answers with the pair rather than with `null`, so
        # no reader has to tell "no handoff yet" from "this field does not exist".
        if not merged.get("opens_on"):
            merged["opens_on"] = {"node": None, "from_run": None}
        # BEFORE `status`, and before anything else reads `merged`: a take is
        # displaced by this very write, so the comparison is between what was
        # stored and what is about to be.
        merged["takes"] = storyboard.keep_take(previous, merged)
        merged["status"] = storyboard.shot_status(merged)
        merged["order"] = (
            merged["order"] if merged.get("order") is not None else (index + 1) * 10
        )
        merged["created"] = previous.get("created") or now
        written.append({**merged, "id": shot_id})
        steps.append((_shot_item(scene_id, shot_id, merged), None))

    steps += [
        (_delete(_entity_pk(ENTITY_SCENE, scene_id), f"{SHOT_PREFIX}{shot_id}"), None)
        for shot_id in existing
    ]
    steps += _shot_run_edges(scene_id, lib, written, now)

    for start in range(0, len(steps), TRANSACTION_ITEMS):
        _write(steps[start : start + TRANSACTION_ITEMS])
    written.sort(key=lambda entry: entry.get("order") or 0)
    return written


def update_shot(scene_id: str, lib: str, shot_id: str, changes: dict) -> dict:
    """One shot: which run rendered it, which panel it came from, its plan.

    The same field list as `put_shots`, because a shot patched one field at a
    time and a shot rewritten by a plan revision are the same row; a narrower
    list here would silently discard whatever the other had just written.
    """
    entry = next((item for item in shots(scene_id) if item["id"] == shot_id), None)
    if entry is None:
        raise NotFoundError(shot_id)

    merged = {**entry, **{k: v for k, v in changes.items() if k in SHOT_FIELDS}}
    # The one-field patch route reaches this too: `scenes render` and
    # `scenes attach` both record a run through here, so a retry that never
    # touches the plan still keeps the take it displaced.
    merged["takes"] = storyboard.keep_take(entry, merged)
    merged["status"] = storyboard.shot_status(merged)
    others = [item for item in shots(scene_id) if item["id"] != shot_id]
    _write([(_shot_item(scene_id, shot_id, merged), None),
            *_shot_run_edges(scene_id, lib, [*others, merged], _now())])
    return merged


# ──────────────────────── where an image came from ────────────────────────


def source_of(record: dict) -> dict:
    """WHY a node is being sent to a model, derived from where it sits.

    **Derived rather than reported, and that is what makes it one answer.** The
    pipeline knows perfectly well that an image is a character's third face
    reference, because `engine/submit.py::gather` just chose it that way — but
    the pipeline is not the only thing that creates runs, and a run backfilled
    from history has no `gather` behind it at all. Deriving provenance here means
    a run submitted today and a run reconstructed from 2026 describe their images
    in the same words, computed by the same code.

    The deepest entity wins, exactly as `owner_of` decides it: a frame under a
    run's `output/` reports the run, not the project the run sits in.

        {"kind": "character", "character": …, "group": "face", "order": 3000}
        {"kind": "run",       "run": …,       "output": 2}
        {"kind": "input-pool", "project": …,  "position": 4}
        {"kind": "object"}

    `object` is the honest fallback and not a failure: a file somebody made a
    folder for and dropped an image into belongs to nobody in particular, which
    is a real answer.
    """
    chain = entity_chain(record)
    owner = chain[0] if chain else None
    if owner is None:
        return {"kind": "object"}

    kind = entity_kind(owner)
    if kind == ENTITY_CHARACTER:
        # **No group, and no order.** What the picture is is on the picture —
        # its own `tags`, which every listing already carries — so saying it
        # here would be a second copy of a fact that has one home.
        return {"kind": "character", "character": owner}

    if kind == ENTITY_RUN:
        source = {"kind": "run", "run": owner}
        try:
            outputs = entity(ENTITY_RUN, owner).get("outputs") or []
        except NotFoundError:
            return source
        if record["node_id"] in outputs:
            # 1-based, because that is what a runref's `#2` means.
            source["output"] = outputs.index(record["node_id"]) + 1
        return source

    if kind == ENTITY_PROJECT:
        # **Position, because `--input N` IS a position** — the working pool is
        # addressed by where a file sorts in it, so a send that recorded only
        # "from the input pool" would lose the part a person actually typed.
        # Imported here rather than at the top: `layout` imports this module, so
        # the dependency only runs one way at import time. The constant is not
        # copied, because a second spelling of "input" is a second answer to
        # which folder `--input N` counts.
        from studio_core.services import layout

        parent = (records([record["parent_id"]]).get(record["parent_id"])
                  if record.get("parent_id") else None)
        if parent and parent.get("name") == layout.INPUT_FOLDER:
            siblings = sorted(
                (child for child in records(
                    [entry["node_id"] for entry in children(parent["node_id"])]
                ).values() if child.get("kind") == KIND_FILE),
                key=lambda node: node["name"],
            )
            for position, node in enumerate(siblings, 1):
                if node["node_id"] == record["node_id"]:
                    return {"kind": "input-pool", "project": owner, "position": position}
        return {"kind": "project", "project": owner}

    return {"kind": "object"}


# ───────────────────────────── sends ─────────────────────────────
#
# One row per image a run binds, and it is to a run what `SHOT#` is to a scene:
# an ORDERED CHILD, not an edge. It exists in a plan before anything has been
# submitted, its identity is its position, and the node it names is a field.
#
# **The order is the meaning, not a presentation detail.** A model is handed a
# list of images and the prompt cites positions in it — a production prompt in
# this library reads "the FIRST image is an existing reference of him" — so a send
# that came back in a different order would make reference *n* the wrong one. That
# is why the sort key is a zero-padded number: a range query returns bind order
# without anything having to sort it afterwards.
#
# A bare `{field: [node, …]}` map on the record would record WHAT was sent and
# lose WHY: `engine/submit.py::gather` decides that an image is a start frame or
# a reference, and which character group it came from. `role` and `source` are
# that reasoning, kept.


SEND_PREFIX = "SEND#"

#: What an image is FOR. The same four words a storyboard panel uses, minus
#: `sample` — a sample binds to nothing, so it never becomes a send.
SEND_ROLES = frozenset({"start", "end", "reference", "input"})

#: Everything a send row holds. All four are AUTHORED; a send has no recorded
#: half, which is the one way it differs from a shot. That is also why
#: `put_sends` replaces rather than merging: there is nothing underneath a
#: revision that a render could have put there.
SEND_FIELDS = ("field", "role", "node", "source")


def _send_sk(order: int) -> str:
    """`SEND#0007`. Zero-padded so the key sorts numerically as a string.

    Four digits, because a model that took more than 9,999 reference images
    would have other problems. `%d` would sort `SEND#10` before `SEND#2`.
    """
    return f"{SEND_PREFIX}{order:04d}"


def sends(run_id: str) -> list[dict]:
    """One run's bound images, in bind order.

    No sort afterwards: the key IS the order, so the query returns them right.
    """
    items = _query(
        TableName=config.catalog_table(),
        KeyConditionExpression="pk = :pk AND begins_with(sk, :send)",
        ExpressionAttributeValues={
            ":pk": {"S": _entity_pk(ENTITY_RUN, run_id)},
            ":send": {"S": SEND_PREFIX},
        },
    )
    entries = []
    for index, item in enumerate(items, 1):
        entry = _entity(item)
        entry["order"] = index
        entries.append(entry)
    return entries


def _send_item(run_id: str, order: int, entry: dict) -> dict:
    return _put(
        _entity_pk(ENTITY_RUN, run_id),
        _send_sk(order),
        {
            **{field: entry.get(field) for field in SEND_FIELDS},
            "created": entry.get("created") or _now(),
        },
    )


def put_sends(run_id: str, entries: list[dict]) -> list[dict]:
    """Replace a run's sends wholesale, renumbered from 1.

    **A replace, where `put_shots` merges, and the difference is not an
    oversight.** A shot carries recorded work — the run that rendered it, the
    clip, the panel — so a plan revision has to land *onto* it. Every field of a
    send is authored, so there is nothing to preserve and merging would only
    make position ambiguous: the whole point of the row is that send 3 is the
    third image, and a merge that kept a dropped send at position 3 would leave
    the list describing an order the model was never given.

    Rows beyond the new length are deleted in the same write, so the tail of a
    shortened list cannot survive as a send nothing sent.
    """
    existing = sends(run_id)
    steps = [(_send_item(run_id, index, entry), None)
             for index, entry in enumerate(entries, 1)]
    steps += [
        (_delete(_entity_pk(ENTITY_RUN, run_id), _send_sk(order)), None)
        for order in range(len(entries) + 1, len(existing) + 1)
    ]

    for start in range(0, len(steps), TRANSACTION_ITEMS):
        _write(steps[start : start + TRANSACTION_ITEMS])
    return [{**{field: entry.get(field) for field in SEND_FIELDS}, "order": index}
            for index, entry in enumerate(entries, 1)]


# ──────────────────────── the submission fingerprint ────────────────────────
#
# Both derivations live in `services/digest.py` and are re-exported at the top
# of this module, so `catalog.plan_digest` and `catalog.submission_fingerprint`
# name them. They live there because this module imports boto3 and the
# pipeline's test fake cannot: it loads `digest.py` and gets the real hash.


# ────────────────────────── the reference spec ──────────────────────────
#
# HOW A REFERENCE PROMPT IS WRITTEN, AS ROWS — the shared prose blocks and the
# per-angle templates that a turnaround fills from a character's bible.
#
# In the table rather than in a file the pipeline ships, so the SPA can read a
# prompt and change one without a code change, a review and a release — prose
# whose whole nature is that it is tuned against what a model actually returned.
# The same argument `POST /api/prompt` makes for video prompts, one tier down.
#
# **Rows rather than one document under `config/`.** A single blob means one
# bad edit takes out every template at once, two editors racing overwrite each
# other wholesale rather than per-field, and nothing can be read without
# parsing the whole. A block is a row, a template is a row, and a UI form edits
# one of them.
#
# `SPEC#BLOCK#<name>` and `SPEC#TEMPLATE#<id>` share the `SPEC#` prefix so the
# whole spec is one `begins_with`, and sort so every block precedes every
# template — which is also the order they have to be assembled in, since a
# template cites blocks by name.
#
# WHAT IS DELIBERATELY NOT HERE: the model, the aspect ratio and the moderation
# setting. Those are engine configuration rather than prose — a wrong one is a
# payload the provider rejects, not a worse sentence — so they stay in code where
# preflight already covers them.

SPEC_PREFIX = "SPEC#"
BLOCK_PREFIX = f"{SPEC_PREFIX}BLOCK#"
TEMPLATE_PREFIX = f"{SPEC_PREFIX}TEMPLATE#"

#: What a template row carries besides its NAME, which is its key.
#:
#: `description` and `tags` are read at PROMOTION rather than at render — they
#: are what somebody starts from when the image this makes becomes identity — so
#: they belong to the template and not to the prompt.
TEMPLATE_FIELDS = ("name", "prompt", "description", "tags")

#: The longest a template may be called.
MAX_TEMPLATE_NAME = 120


def clean_template_name(raw: str | None) -> str:
    """A template's name — a LABEL, not its key.

    **The record is keyed on a UUID**: this table holds no name claims, so a
    name here identifies nothing and is not unique. Keying on the name would
    strand any field that points at a template — "which template did this run
    start from" is an obvious one.

    A block is the one exception, and has the reason a template lacks: it
    is cited by name IN PROSE, `{block.face_only}`, so a UUID there would name
    something no template could write.

    So this only folds whitespace. `#` is refused rather than escaped because it
    separates the segments of every key in this table; the rest is left alone,
    so a template may be called `Body, back` and read like the thing it is.
    """
    name = " ".join((raw or "").split())
    if not name:
        raise ValidationError("a template needs a name")
    if "#" in name:
        raise ValidationError("a template name may not contain '#'")
    if len(name) > MAX_TEMPLATE_NAME:
        raise ValidationError(
            f"a template name is at most {MAX_TEMPLATE_NAME} characters")
    return name


def templates(lib: str) -> dict:
    """The whole library: `{"blocks": {name: text}, "templates": [template, ...]}`.

    One query. Blocks come back as a mapping because that is what a template
    fills from, and templates as a list, sorted by name.

    **There is no `order`.** A template is picked for one run, so the only
    order that matters is the one a person reads a list in, and that is
    alphabetical.
    """
    items = _query(
        TableName=config.catalog_table(),
        KeyConditionExpression="pk = :pk AND begins_with(sk, :spec)",
        ExpressionAttributeValues={":pk": {"S": _lib_pk(lib)}, ":spec": {"S": SPEC_PREFIX}},
    )
    blocks, found = {}, []
    for item in items:
        record = _entity(item)
        sk = item["sk"]["S"]
        if sk.startswith(BLOCK_PREFIX):
            blocks[sk.removeprefix(BLOCK_PREFIX)] = record.get("text") or ""
        elif sk.startswith(TEMPLATE_PREFIX):
            found.append({
                "id": sk.removeprefix(TEMPLATE_PREFIX),
                "name": record.get("name") or "",
                **{k: record.get(k) for k in TEMPLATE_FIELDS if record.get(k) is not None},
            })
    found.sort(key=lambda entry: entry["name"].lower())
    return {"blocks": blocks, "templates": found}


def put_spec_block(lib: str, name: str, text: str) -> dict:
    """Write one shared block. An overwrite, because a block IS its name."""
    record = {"name": name, "text": text, "updated": _now()}
    _write([(_put(_lib_pk(lib), f"{BLOCK_PREFIX}{name}", record), None)])
    return record


def put_template(lib: str, template_id: str, fields: dict) -> dict:
    """Write one template. Unknown keys are dropped rather than stored.

    Dropping rather than refusing: a caller that round-trips `templates` hands
    back `id` and whatever the read added, and rejecting those would make the
    obvious edit-then-save flow fail on fields it produced itself.

    **One row, and a rename is a field write.** A name is a LABEL and identity
    is the id. Nothing resolves a template by name, so a duplicate is a display
    problem rather than an ambiguity, and it costs a person nothing they cannot
    fix by renaming one.
    """
    record = {k: v for k, v in fields.items() if k in TEMPLATE_FIELDS}
    record["updated"] = _now()
    _write([(_put(_lib_pk(lib), f"{TEMPLATE_PREFIX}{template_id}", record), None)])
    return {"id": template_id, **record}


def delete_template(lib: str, template_id: str) -> None:
    _write([(_delete(_lib_pk(lib), f"{TEMPLATE_PREFIX}{template_id}"), None)])


def delete_spec_block(lib: str, name: str) -> None:
    _write([(_delete(_lib_pk(lib), f"{BLOCK_PREFIX}{name}"), None)])


# ─────────────────────────── the phrasebook ───────────────────────────
#
# A per-model list of avoid/use pairs, one row per pair. There is no document
# to create first, so `phrasebook add` cannot fail on an empty library.


TERM_PREFIX = "TERM#"


def terms(lib: str, model: str | None = None) -> list[dict]:
    """The wording list, optionally for one model.

    `TERM#<model>#<avoid>` sorts by model and then by the word, so a single-model
    read is a `begins_with` rather than a filter — which is why the model comes
    first in the key even though the pair is what makes a term unique.
    """
    prefix = f"{TERM_PREFIX}{model}#" if model else TERM_PREFIX
    items = _query(
        TableName=config.catalog_table(),
        KeyConditionExpression="pk = :pk AND begins_with(sk, :term)",
        ExpressionAttributeValues={":pk": {"S": _lib_pk(lib)}, ":term": {"S": prefix}},
    )
    return [_entity(item) for item in items]


def add_term(lib: str, model: str, avoid: str, use: str, note: str | None = None,
             replicate: str | None = None) -> dict:
    """Claim one avoid/use pair. A duplicate is a 409, not an overwrite.

    Conditional, for the reason every claim here is: the pair *is* the key, so
    "already there" is a condition failure rather than a read somebody raced.

    `replicate` is `<owner>/<name>`, carried for display and stored per row
    rather than per model — there is no model row to hang it off, and a term is
    the only thing this table knows about a model.
    """
    now = _now()
    record = {"model": model, "avoid": avoid, "use": use, "note": note,
              "replicate": replicate, "created": now}
    _write(
        [
            (
                _put(_lib_pk(lib), f"{TERM_PREFIX}{model}#{avoid}", record, unique=True),
                ConflictError(f"'{avoid}' is already listed for {model}"),
            )
        ]
    )
    return record


def delete_term(lib: str, model: str, avoid: str) -> None:
    _write([(_delete(_lib_pk(lib), f"{TERM_PREFIX}{model}#{avoid}"), None)])


# ──────────────────────────── render jobs ────────────────────────────
#
# A RENDER JOB IS A ROW, AND DELIBERATELY NOT A SIXTH ENTITY.
#
# Stitching, frame extraction and contact sheets run on a worker Lambda (see
# `services/render.py`), so the caller has to be told when the work finished.
# Polling the scene or movie record — both carry a status — does not go as far
# as `frames grid`, which produces an image belonging to no scene, or as far as
# reporting *why* something failed, since a scene's `error` is one field for
# every kind of failure a scene can have.
#
# So a job has a row of its own: `pk = RENDER#<id>`, `sk = META`. It is not an
# entity — no `ENTITY_KEYS` prefix, no listing projection, no
# `by-recent` presence, nothing in `docs/ENTITY_MODEL.md`. The precedent above it
# in this file is `SWEEP#`: bookkeeping the service writes about work in flight,
# read by the machinery and not by a person browsing a library.
#
# **There is no listing.** A job is addressed by the id its enqueue returned, and
# nothing walks them. That is a real limitation — nothing answers "what is stuck"
# — and the thing that does answer it is the dead-letter alarm in
# `modules/render`, which fires on a message that ran out of retries. A listing
# is a second row (a `LIB#` sort key carrying the timestamp) and can be added the
# day a person wants a page of them; adding it now would be a projection nothing
# reads.
#
# `lib` is on the row because the worker has no request and therefore no
# `g.library`, and because `GET /api/renders/<id>` has to check the caller is in
# it — an id is a v4 UUID, but "unguessable" is not an authorization model.

RENDER_PREFIX = "RENDER#"

#: A job that has been accepted and not yet picked up, one that a worker holds,
#: and the two ways it ends. `succeeded`/`failed` mirror `RUN_STATUSES` rather
#: than inventing `done`/`error`, so a reader who knows what a run's status
#: means knows what a render's does.
RENDER_STATUSES = frozenset({"queued", "running", "succeeded", "failed"})

TERMINAL_RENDER_STATUSES = frozenset({"succeeded", "failed"})


def _render_pk(render_id: str) -> str:
    return f"{RENDER_PREFIX}{render_id}"


def create_render(lib: str, kind: str, params: dict) -> dict:
    """Write a queued job row. -> the record, whose `id` is what a caller polls.

    Written **before** the message is enqueued, so a worker cannot receive a job
    whose row does not exist yet. The other order has a real race: SQS delivery
    is fast enough that a worker has read a missing row in production systems
    built the other way round, and there is nothing sensible to do about it from
    the worker's side.

    The cost of this order is the opposite failure — a row written and a
    `SendMessage` that then throws — which leaves a job `queued` forever. That is
    visible (the poller times out saying so) rather than silent, and it spends
    nothing.
    """
    render_id = f"render-{uuid.uuid4()}"
    now = _now()
    record = {"id": render_id, "lib": lib, "kind": kind, "params": params,
              "status": "queued", "result": None, "error": None,
              "created": now, "updated": now}
    _write([(_put(_render_pk(render_id), META, record, unique=True), None)])
    return record


def render(render_id: str) -> dict:
    """One job row, by id."""
    if not render_id.startswith("render-"):
        raise NotFoundError(render_id)
    try:
        response = dynamodb.client().get_item(
            TableName=config.catalog_table(),
            Key={"pk": {"S": _render_pk(render_id)}, "sk": {"S": META}},
        )
    except ClientError as exc:
        logger.warning("GetItem failed for %s: %s", render_id, exc)
        raise UpstreamError("Could not read the catalog") from exc
    item = response.get("Item")
    if not item:
        raise NotFoundError(render_id)
    # `_entity`, not `_attributes`, and the difference is `_numbers`. A job's
    # `params` carry `cols`, `cell`, `count`, `at` — every one of which comes back
    # from DynamoDB as a `Decimal`, and `Image.new` refuses one with
    # `'decimal.Decimal' object cannot be interpreted as an integer`. The
    # validation on the way in is done against the request's JSON, so nothing
    # before this read would notice.
    return _entity(item)


def update_render(render_id: str, **assignments) -> dict:
    """Move a job on. Unconditional — one worker holds one message at a time.

    No `rev` and no condition beyond the row existing, for the reason
    `routes/scenes.py` gives about a scene: this record is driven by a machine
    in sequence, not edited by two people at once. SQS's visibility timeout is
    what stops two workers holding the same job, and a redrive of a job that
    already succeeded is idempotent because the assignments are absolute rather
    than incremental.
    """
    if "status" in assignments and assignments["status"] not in RENDER_STATUSES:
        raise ValidationError(f"'{assignments['status']}' is not a render status")
    assignments["updated"] = _now()
    _write([(_update({"pk": {"S": _render_pk(render_id)}, "sk": {"S": META}},
                     assignments), NotFoundError(render_id))])
    return render(render_id)
