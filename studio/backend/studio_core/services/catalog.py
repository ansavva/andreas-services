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
| Character slug claim | `LIB#<lib>` | `CHARSLUG#<slug>` | uniqueness, and the listing |
| Reference entry | `CHAR#<char_id>` | `REF#<node_id>` | one row per reference image |
| Project | `PROJ#<proj_id>` | `META` | the record |
| Project slug claim | `LIB#<lib>` | `PROJSLUG#<slug>` | uniqueness, and the listing |
| Project ↔ character | `PROJ#<proj_id>` | `CHAR#<char_id>` | involvement; reverse-queryable |
| Run | `RUN#<run_id>` | `META` | the envelope |
| Run in project | `PROJ#<proj_id>` | `RUN#<created>#<run_id>` | newest first, paginated |
| Run ↔ character | `RUN#<run_id>` | `CHAR#<char_id>` | which characters a run used |
| Scene / Movie | `SCENE#…` / `MOVIE#…` | `META` | |
| Scene / Movie in project | `PROJ#<proj_id>` | `SCENE#<created>#<id>` | |
| Shot | `SCENE#<scene_id>` | `SHOT#<shot_id>` | one row per planned shot |
| Phrasebook term | `LIB#<lib>` | `TERM#<model>#<avoid>` | the wording lists |

**An id is the identity; a slug is a label.** Every entity has a `v4` UUID that
never changes, and the slug is a mutable, library-unique attribute. A rename is
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
  sense** — a node is in the library its parent is in — and `transfer_node`
  rewrites it across a branch under the same ordering rule.
* **`blob_key` is stamped once and never re-derived.** It is built by
  `blob_key_for` at creation, from the owner the parent already resolves to, and
  after that it is a pointer that nothing splits, rewrites or recomputes. Prod
  also holds `characters/<slug>/…` keys written years before this table existed,
  and they stay correct forever precisely because the text carries no meaning to
  any reader. The one thing that reads a key is `is_api_blob`, which looks at the
  **tail** — `<node_id>.<ext>`, which cannot change — and never at the prefix,
  which drifts the moment a node moves between owners.

## The library root is an ordinary node

`root_node` on the library names a real `NODE#<id>`/`META` row, with `path`
`"/"` and **no** `parent_id`. #280 does not say so either way; the alternative —
a root that is only an id on the library item — means every function that needs
a parent's `path` has a special case for "the parent is the root", and
`create_node` would have to read the library to find out. A root that is a node
costs one row and removes that branch everywhere.

Its missing `parent_id` is then load-bearing: it is what makes "rename the
library root", "move it" and "delete it" refuse, since there is no `NAME#` item
to rewrite. That is the same refusal `keys.assert_inside_root` used to make from
a string comparison against the media root, arrived at from the data instead —
which is why that function had no caller left and went with #312.

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
from studio_core.services import keys

logger = logging.getLogger(__name__)

KIND_FOLDER = "folder"
KIND_FILE = "file"
KINDS = frozenset({KIND_FOLDER, KIND_FILE})

# The role a membership row carries. `owner` is named here because a route
# compares against it — `transfer_node`'s caller must hold it in both libraries —
# and the string is written by `scripts/add-member.sh`, which is the only thing
# that creates a membership. Nothing in this module reads or enforces a role:
# membership is authorisation and it is checked above, against the node's own
# `lib`. The other value is `member`, and it is not named because no code
# branches on it.
ROLE_OWNER = "owner"

# `by-path` is the subtree index: hashed on `lib`, ranged on `path`, so one
# `begins_with` reads a whole branch.
#
# **`by-recent` is hashed on `reel`, which holds the library id and is not
# `lib`.** The two carry the same string and that is exactly why the distinction
# has to be spelled out: a DynamoDB item enters a GSI only when it carries both
# of that index's key attributes, so what the attribute is *named* decides who is
# in the index. `reel` is written onto file nodes whose extension reads as an
# image or a video and onto nothing else — so folder nodes, entity records,
# membership rows, slug claims and reference rows all carry `lib`, all carry a
# timestamp, and all stay out.
#
# That is a fix rather than accommodation for the entity rows. Hashed on `lib`,
# every folder in the library entered the reel's enumeration and was filtered out
# in memory by `browse.reel_items` — after it had already been counted against
# `config.max_folder_objects`. A sparse index spends the cap on rows the reel can
# actually show.
#
# `by-sk` inverts the table so a sort key can be asked who points at it. It used
# to have `scripts/add-member.sh` as its only consumer; the entity model made it
# load-bearing — "every project involving this character" is
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

# The two kinds whose slug is unique in a library, and the claim that makes it
# so. A run, a scene and a movie have a slug too — it is a human label, several
# of them may read the same, and nothing addresses one by it.
CLAIM_PREFIX = {ENTITY_CHARACTER: "CHARSLUG#", ENTITY_PROJECT: "PROJSLUG#"}

# The three kinds a project lists, and the folder each one's tree hangs under.
# `services.layout` owns the folder *names*; this is only the set.
PROJECT_ENTITIES = (ENTITY_RUN, ENTITY_SCENE, ENTITY_MOVIE)

# What `counts` on a project record holds, keyed by the entity kind that moves
# it. Maintained inside the transaction that creates or deletes the entity, so a
# count is never a scan and never drifts by one.
COUNT_FIELD = {ENTITY_RUN: "runs", ENTITY_SCENE: "scenes", ENTITY_MOVIE: "movies"}

# The version of the character profile shape this API validates against. On the
# record rather than inside `profile`, because it describes the map rather than
# being part of it.
PROFILE_SCHEMA_VERSION = 2

# What a run's `status` may be. Studio owns this word — it is the one thing about
# a submission this service is willing to have an opinion on — while the
# provider's own response stays an undecoded blob beside it.
RUN_STATUSES = frozenset({"pending", "running", "succeeded", "failed", "cancelled"})

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
    type and boto3 will not guess a binary-float rounding for you. Nothing in
    this table held one until a run started recording what a prediction cost,
    and `{"amount": 0.032}` arriving from a JSON body is a float every time.

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

    Microseconds because this is the timestamp the reel will sort on, and the
    thing it replaces — S3's `LastModified` — has one-second resolution while a
    run writes its whole output inside one second. `browse._sort_files` breaks
    ties on the key to survive that; a timestamp that does not collide is what
    retires the workaround.
    """
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _node_pk(node_id: str) -> str:
    return f"NODE#{node_id}"


def _name_sk(name: str) -> str:
    return f"NAME#{name}"


def _lib_pk(lib: str) -> str:
    """The library's own partition.

    The same text a membership row carries as its *sort* key, and that the two
    agree is the mechanism rather than a coincidence: a membership is filed under
    the *user*, so the inverted `by-sk` index reaches every member of a library by
    asking for the string the library itself is keyed on. There used to be a
    `_lib_sk` here spelled apart from this one to say so; it went with
    `members_of`, and `scripts/add-member.sh` is what asks that question now.
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

    **Both halves of a node sit in `by-path` and `by-recent`** — #280 puts `lib`,
    `path` and `created_at` on the by-parent item too — so an unfiltered query
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
    `content_type`.** The by-parent item carries the index projection #280
    defines and nothing more, so a listing that wants a file's size is one query
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
    projection** #280 defines — `node_id`, `lib`, `kind`, `path`, `created_at`,
    plus the `name` carried in the sort key — and not the full record. A caller
    that needs `blob_key` or `size` for one entry fetches it with `node`.

    That is a deliberate reading of the schema rather than an oversight: the
    projection is what makes a listing one query, and widening it would mean
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

    **Every row this returns is already something the reel can show**, which it
    was not before. `by-recent` is hashed on the sparse `reel` attribute, so a
    folder, an entity record and a slug claim are absent from the index rather
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
    is gone" (404) — DynamoDB reports which item was cancelled and in which
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
    # and every reader here already understand. It became load-bearing with the
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
# carries no name, so a listing of the PRODUCTION bucket stops leaking hard
# rule #1. That half of the rule is unchanged by the rule going env-scoped: a
# dev subject may be named in the repo, and a production character still may
# not be named anywhere — including in a key nobody thought of as prose.
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

# The second segment of every key this API has ever stamped: an entity or
# library id. No legacy key had one — those were `characters/<slug>/…`, where a
# slug is a name a person chose.
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

    **It reads the SHAPE of the first two segments, and this used to read the
    tail.** That was `/<node_id>.<ext>`, which was every key this API had ever
    written — until the key became descriptive and its last segment became the
    file's own name. `reseat --apply` then rewrote production to the new shape
    and every one of its 186 file nodes stopped matching, so both upload routes
    refused to overwrite anything in the library. Measured, not theorised.

    So the test is `<owner_prefix>/<entity-or-library id>/…`: one of the three
    prefixes, then an id. That holds for the flat keys this API stamps AND for
    the descriptive ones the reseat of that era left in production, which is
    what makes it correct while the two coexist — and they still do. `reseat`
    builds a flat key again and clears them, but until it has been run against a
    given library both shapes are live in it.

    **It is still not a check on WHICH owner.** The prefix says who owned the
    node when the key was stamped and drifts the moment the node moves, so
    reading the id itself would start refusing uploads to a file somebody
    dragged into another folder. Only the shape is read; the values are not.

    The two upload routes share this so they cannot disagree about which objects
    are writable through a signature — a distinction a signed URL makes permanent
    the moment it is handed out. A key of any other shape predates the catalog
    (#309) — `characters/<slug>/…`, `blobs/<node_id>`, `config/pose/…` — and
    overwriting bytes written before this table existed is not what those routes
    are for.
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
    """The entity a node belongs to, as `{kind, id, slug}`, or `None`.

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
            # A reverse pointer naming a record that is gone. Skipped rather than
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
    #280 defines a folder as a node with no blob. Size and content type are
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

    An explicit `blob_key` is still stored exactly as given, because prod holds
    keys written long before this table did.
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
    `keys.numbered_name` owns and `manage.copy_objects` has produced since #317.
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
#: and would be a second thing to keep correct; references have been free-form
#: since `--pick-tag` existed, and the tags there converged without one.
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

    **This is on the node rather than on a `REF#` row, and that was a decision
    rather than an obvious place.** A description used to live on the reference
    entry, so the same image described as a character's identity carried its
    description in a row belonging to the character-image *relationship*. That is
    the right home for `group` and `order`, which are facts about the set. It is
    the wrong home for "head and shoulders in full profile" — which is a fact
    about the picture, true whether or not anybody ever made it a reference.

    The cost of the old home was visible in this library: twelve files sat in
    `reference/` folders with no row and therefore no description anywhere, and a
    legacy `profile.corpus` list was the only thing holding descriptions for
    some of them.

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

    The reference routes still take `description` and `tags` — a person editing a
    caption in the reference grid should not have to know that the caption is
    stored somewhere else — so they compose these onto a node update in the same
    transaction as the `REF#` row. One validator, so a tag typed in the grid and
    a tag typed in the file browser are folded the same way.
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


def _describe_step(node_id: str, entry: dict, now: str):
    """The node half of a reference write, or nothing if it says nothing.

    Returns `None` when the caller mentioned neither field, so an attach that
    only sets a group does not touch the node's row at all.
    """
    assignments = describe_assignments(
        entry.get("description", ...), entry.get("tags", ...)
    )
    if not assignments:
        return None
    assignments["updated_at"] = now
    return (_update_meta(node_id, assignments), None)


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
    merging two trees. Crossing libraries is refused as well — that is
    `transfer_node` below, which rewrites `lib` across the branch and carries
    membership implications a move does not. **Do not relax this refusal to make
    a transfer easier**: the two operations differ in who is allowed to ask for
    them, and a move that could change `lib` would be a transfer that skipped the
    ownership check in the destination library.
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


def transfer_node(node_id: str, lib: str) -> dict:
    """Carry a node, and everything beneath it, into another library.

    **Zero objects move, and if an implementation here ever reaches for
    `CopyObject` the model is wrong rather than the code.** A blob is addressed
    by a key nothing parses, and which library a node belongs to is an attribute
    on a row. Rewriting the attribute is the entire operation; the bytes are not
    involved and are not even read. `tests/integration/test_transfer.py` asserts
    that against a real bucket, because a mock's call log would pass on any code
    that copied through some other path.

    **A whole subtree or nothing.** The unit is a node — a project, a character,
    a run — and everything under it, never a scattering of files chosen
    individually. Run records name their inputs by node, so a branch stays
    internally consistent when it moves as one batch and stops being consistent
    the moment half of it is somewhere else. `subtree` bounds it at
    `STUDIO_MAX_FOLDER_OBJECTS` and refuses rather than truncating, for the
    reason stated there.

    **It lands on the destination library's root**, not on a folder inside it.
    One library id is the whole request, and where it goes next is an ordinary
    `move_node` the caller can now make, because the node is in their library.
    Taking a destination folder as well would be a second thing to authorise and
    a second way to name the wrong library.

    **Two writes, target first, and the order is `move_node`'s for `move_node`'s
    reason.** `parent_id` is the one attribute nothing can reconstruct; `lib` and
    `path` are both derivable from it by walking parents, so they are the safe
    half to leave half-written. That order also puts the name collision — a
    conditional put — before anything else is touched, so a 409 here has written
    nothing at all, which is what "a refusal rather than a partial transfer"
    requires.

    **The cost of that order, stated rather than hidden:** an interruption
    between the two writes leaves the node in its new library with descendants
    still in the old one, and re-running does *not* repair it — the second run
    sees a node already where it was asked to go. The subtree is still reachable
    by `parent_id` the whole time, and `lib` can be rebuilt from it, but nothing
    here does that today. Unlike `delete_node`, this one does not finish itself.
    """
    record = node(node_id)
    if not record.get("parent_id"):
        raise ValidationError("the library root cannot be transferred")
    if lib == record["lib"]:
        # Already where it was asked to go. Not an error, and not a write: the
        # same reading `move_node` gives a destination that is the current
        # parent.
        return {**record, "transferred": False, "descendants": 0}

    # `library` raises `NotFoundError` for an id naming no row, which is what a
    # membership pointing at nothing looks like — see `routes/libraries.py`.
    # `_folder_node` then reads the root it names, so a library whose root is
    # missing fails here rather than after the subtree has been rewritten.
    destination = _folder_node(library(lib)["root_node"])
    branch = child_path(record)
    # Read before the first write. Afterwards the node's own `path` and `lib`
    # name the destination while its descendants still name the source, so this
    # query has one answer only while it is asked first.
    descendants = subtree(record["lib"], branch)

    now = _now()
    transferred = {
        **record,
        "parent_id": destination["node_id"],
        "lib": lib,
        "path": child_path(destination),
        "updated_at": now,
    }

    assignments = {
        "parent_id": destination["node_id"],
        "lib": lib,
        "path": transferred["path"],
        "updated_at": now,
    }
    if record["kind"] == KIND_FILE:
        assignments["reel"] = _reel_value(record["name"], lib)
        transferred["reel"] = assignments["reel"]

    _write(
        [
            (_delete_name(parent_id=record["parent_id"], name=record["name"]), None),
            (
                _put_name(transferred, parent_id=destination["node_id"], name=record["name"]),
                ConflictError(f"'{record['name']}' already exists there"),
            ),
            (_update_meta(node_id, assignments), NotFoundError(node_id)),
        ]
    )

    _rewrite_branch(descendants, old=branch, new=child_path(transferred), lib=lib)

    logger.info(
        "Transferred %s from %s to %s (%d descendants)",
        node_id,
        record["lib"],
        lib,
        len(descendants),
    )
    return {**transferred, "transferred": True, "descendants": len(descendants)}


def _rewrite_branch(
    descendants: list[dict], *, old: str, new: str, lib: str | None = None
) -> None:
    """Re-materialise `path` — and, for a transfer, `lib` — on a moved branch.

    Both halves of every node, because the by-parent item carries `path` and
    `lib` too and `by-path` is hashed on the one and ranged on the other: a
    descendant rewritten on the record half alone would be indexed under a
    library it is no longer in. Two writes per descendant is what fixes the batch
    at fifty nodes.

    Only the prefix of `path` changes. The part below the moved node describes
    ancestors that moved with it and is copied across untouched.

    `lib` is optional because a move never changes it — the destination is in the
    same library or `move_node` refused — and assigning it there would be a
    second writer of the attribute every GSI partitions on, for no change.

    **A transfer also has to carry `reel`, because its value *is* the library
    id.** Miss it and every image in the branch stays in the source library's
    reel while its row says it belongs to another — a leak of exactly the kind
    the membership checks exist to prevent, and one that no folder listing would
    show. Only on the record half: `by-recent` reads `reel` and `created_at`, and
    the by-parent item carries neither, so writing it there would put a second
    copy of every file in the index.
    """
    steps: list[tuple[dict, Exception | None]] = []
    for record in descendants:
        path = new + record["path"][len(old):]
        assignments = {"path": path} if lib is None else {"path": path, "lib": lib}
        meta_assignments = dict(assignments)
        if lib is not None and record["kind"] == KIND_FILE:
            meta_assignments["reel"] = _reel_value(record["name"], lib)
        steps.append(
            (
                _update_meta(record["node_id"], {**meta_assignments, "updated_at": _now()}),
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
    a record naming a node that is gone is the one broken state this model cannot
    repair from the tree. The refusal says which entity to delete instead.

    `allow_entities` is for the entity deletes themselves, which have already
    removed the record and its links and are finishing the job. It is not a
    force flag for a caller who finds the refusal inconvenient.

    Nothing in S3 is touched. The `blob_key` values come back so the caller can
    decide what to do about the bytes — two nodes may point at one key, since a
    copy in this model copies a row, so "is this blob now unreferenced" is not a
    question one delete can answer.
    """
    record = node(node_id)
    if not record.get("parent_id"):
        raise ValidationError("the library root cannot be deleted")

    descendants = subtree(record["lib"], child_path(record))
    if not allow_entities:
        _assert_no_entities([record, *descendants])
    descendants.sort(key=lambda entry: len(entry["path"]), reverse=True)
    doomed = descendants + [record]

    steps: list[tuple[dict, Exception | None]] = []
    for victim in doomed:
        steps.append((_delete_name(parent_id=victim["parent_id"], name=victim["name"]), None))
        steps.append((_delete_meta(victim["node_id"]), None))

    for start in range(0, len(steps), TRANSACTION_ITEMS):
        _write(steps[start : start + TRANSACTION_ITEMS])

    logger.info("Deleted %s (%d nodes)", node_id, len(doomed))
    return {
        "node_id": node_id,
        "deleted": len(doomed),
        "blob_keys": [victim["blob_key"] for victim in doomed if victim.get("blob_key")],
    }


def set_blob(
    node_id: str,
    blob_key: str,
    *,
    size: int | None = None,
    content_type: str | None = None,
) -> dict:
    """Point a file node at its bytes.

    The by-parent item is untouched, because #280 does not project `blob_key`,
    `size` or `content_type` onto it — so this is one item, and still a
    transaction. That costs twice the write capacity of a bare `UpdateItem` and
    buys one thing worth having: every write in this module fails the same way,
    through `_write`, with a per-item reason. A single `UpdateItem` here would
    be the one path with its own error handling to keep true.

    `blob_key` is stored exactly as given. It is not validated against a prefix,
    not checked for existence in the bucket, and not derived from `node_id` —
    prod holds keys written long before this table did and they stay where they
    are.
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
# The same two reasons a node is two items, and it is worth stating rather than
# inheriting silently. DynamoDB enforces uniqueness on **one thing only: the
# primary key**, and the two properties an entity needs pull in opposite
# directions:
#
# * The record must be keyed on the **id**, because the id is what every other
#   row points at and it must never change. `CHAR#<char_id>` / `META`.
# * The slug must be **unique in the library**, and the only way to say that to
#   DynamoDB is to make the slug part of a key. `LIB#<lib>` / `CHARSLUG#<slug>`,
#   written under `attribute_not_exists(pk)`.
#
# One item cannot be keyed both ways, so there are two — and the claim item then
# earns its keep a second time as the **list index**: "every character in this
# library" is one query on `LIB#<lib>` rather than the `Scan` this table must
# never have.
#
# **A GSI does not substitute for it.** An index hashed on `lib` and ranged on
# `slug` would give the listing and enforce nothing: two records with the same
# slug both land in it, silently. Uniqueness has to be a condition expression on
# a real key.
#
# **Keying the character on its slug instead** — `LIB#<lib>` / `CHAR#<slug>` —
# collapses it to one item and reintroduces the disease the whole model removes:
# a rename becomes delete-and-recreate, and every `REF#` row, run link and
# binding pointing at it is pointing at a key that no longer exists.
#
# ## The claim is a pointer, never a projection
#
# It carries the entity id and a timestamp and nothing else. Putting
# `display_name` on it would put a mutable copy on a second item that every
# rename has to keep in step — the trap `GET /api/nodes` already avoids by
# pairing a query with a `BatchGetItem`, and the listing here is the same shape
# for the same reason.
#
# **The run listing row is the one deliberate exception**, and it is deliberate
# because a run is immutable once it completes: there is nothing left to keep in
# step, and the runs screen would otherwise need a `BatchGetItem` over hundreds
# of envelopes to draw a grid of thumbnails.
#
# ## `rev` is compare-and-swap, not check-then-write
#
# Every mutation of a record carries the `rev` the caller last read and fails the
# transaction if it moved. That closes a window that was open: the old
# `write_profile` re-read a node's `updated_at` and refused if it had changed,
# which is a check and a write with a gap between them. A `ConditionExpression`
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


def _claim_sk(kind: str, slug: str) -> str:
    return f"{CLAIM_PREFIX[kind]}{slug}"


def _numbers(value):
    """Turn every `Decimal` a read hands back into an int or a float.

    The deserialiser returns `Decimal` for every N, which is right for money and
    wrong for everything about to be JSON-encoded into a response — `jsonify`
    refuses one outright. `_record` does this for `size` alone because a node has
    exactly one number on it; an entity record has `rev`, three `counts`, a
    reference `order` and a `cost.amount` nested two deep, so this walks.

    Integral values come back as `int` so a `rev` reads as `7` rather than `7.0`
    — a client comparing the two would be right to be confused.
    """
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: _numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_numbers(item) for item in value]
    return value


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
    """`{kind, id, slug}` for one entity — what a node's `owner` reports.

    Deliberately three fields. A listing that drew the whole record per file
    would fetch a profile per thumbnail, and the SPA needs exactly enough to
    write "in <slug>" and link it.
    """
    kind = entity_kind(entity_id)
    record = entity(kind, entity_id)
    return {"kind": kind, "id": record["id"], "slug": record.get("slug")}


def _claims(lib: str, kind: str) -> list[dict]:
    items = _query(
        TableName=config.catalog_table(),
        KeyConditionExpression="pk = :pk AND begins_with(sk, :claim)",
        ExpressionAttributeValues={
            ":pk": {"S": _lib_pk(lib)},
            ":claim": {"S": CLAIM_PREFIX[kind]},
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

    **One query plus a batched read** — the claim rows say which ids exist and
    `BatchGetItem` fetches the records. The same shape `GET /api/nodes` uses, for
    the same reason: the claim stays a pointer rather than a projection somebody
    has to keep in step.

    A claim naming a record that is not there is logged and dropped rather than
    raised. Every create and delete here is one transaction over both items, so
    one without the other means a row was written by hand — and a listing that
    500s over it is a library nobody can open.
    """
    claims = _claims(lib, kind)
    found = entities_by_id(kind, [claim["entity"] for claim in claims])

    listed = []
    for claim in claims:
        record = found.get(claim["entity"])
        if record is None:
            logger.warning("Library %s claims a missing %s: %s", lib, kind, claim["entity"])
            continue
        listed.append(record)
    return listed


def entity_by_slug(lib: str, kind: str, slug: str) -> dict:
    """One entity by the label a person types. Two reads, no scan."""
    try:
        response = dynamodb.client().get_item(
            TableName=config.catalog_table(),
            Key={"pk": {"S": _lib_pk(lib)}, "sk": {"S": _claim_sk(kind, slug)}},
        )
    except ClientError as exc:
        logger.warning("GetItem failed for %s '%s': %s", kind, slug, exc)
        raise UpstreamError("Could not read the catalog") from exc

    item = response.get("Item")
    if not item:
        raise NotFoundError(slug)
    return entity(kind, _entity(item)["entity"])


def linked(entity_id: str, holder_kind: str) -> list[str]:
    """Everything of one kind that points at this entity, read backwards.

    `by-sk` inverts the table, so `sk = CHAR#<id> AND begins_with(pk, "PROJ#")`
    is "which projects involve this character" and the same query one prefix over
    is "which runs used it". Both are questions that have no answer at all in the
    document-shaped model this replaces — the second one is `runs find
    --character`, which lists every project, lists every run in each, reads
    `request.json` for each, and greps.
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


def _tree_steps(parent: dict, slug: str, entity_id: str, layout: tuple) -> tuple[dict, list]:
    """The root folder an entity owns, plus its starting layout, as one write.

    Returns the root record and the steps that create it and its children. The
    root carries `entity` — one attribute, written once, never changed — and it
    is what lets a listing draw a character card instead of a folder icon and
    what `GET /api/nodes/<id>/owner` walks up to. The forward pointer is `root`
    on the record. One field in each direction, and no map of folder names in
    either.
    """
    root = _new_node(parent, slug, KIND_FOLDER, entity=entity_id)
    steps = _node_steps(root)
    for name in layout:
        steps += _node_steps(_new_node(root, name, KIND_FOLDER))
    return root, steps


def create_character(
    lib: str,
    parent_id: str,
    *,
    slug: str,
    display_name: str | None,
    fictional: bool,
    profile: dict,
    layout: tuple,
) -> dict:
    """A character, its slug claim, its root folder and its pools — one write.

    **Twelve items in one `TransactWriteItems`**: the record, the claim, and two
    each for the root and the four starting pools. Either all of it exists or
    none of it does, which is the property that makes "creating a character"
    something a person can retry after a timeout without inspecting what
    survived.

    **The four pools are a starting layout, not a schema.** They exist because an
    empty character is unhelpful; nothing afterwards requires them. Rename
    `reference/`, delete `archive/`, add one of your own — all ordinary file
    operations, and none of them breaks anything, because an image is a reference
    when a `REF#` row says so and not because of the folder it sits in.

    A slug already claimed and a folder name already taken are two different
    condition failures with two different messages, and `_write` is what keeps
    them apart — the claim says "a character called X already exists", the folder
    says "X already exists here", and the second can happen without the first
    when somebody made an ordinary folder by that name.
    """
    parent = _folder_node(parent_id)
    if parent["lib"] != lib:
        raise ValidationError("a character is created in its own library")

    char_id = _mint(ENTITY_CHARACTER)
    now = _now()
    root, tree = _tree_steps(parent, slug, char_id, layout)

    record = {
        "id": char_id,
        "lib": lib,
        "slug": slug,
        "display_name": display_name or slug,
        "fictional": fictional,
        "schema_version": PROFILE_SCHEMA_VERSION,
        "rev": 1,
        "created": now,
        "updated": now,
        "root": root["node_id"],
        "hero": None,
        "default_set": [],
        "profile": profile,
    }

    _write(
        [
            (
                _put(_lib_pk(lib), _claim_sk(ENTITY_CHARACTER, slug),
                     {"entity": char_id, "created": now}, unique=True),
                ConflictError(f"a character called '{slug}' already exists"),
            ),
            (
                _put(_entity_pk(ENTITY_CHARACTER, char_id), META, record, unique=True),
                ConflictError(f"a character called '{slug}' already exists"),
            ),
            *tree,
        ]
    )

    logger.info("Created character %s in %s", char_id, lib)
    return record


def create_project(
    lib: str,
    parent_id: str,
    *,
    slug: str,
    title: str | None,
    description: str | None,
    characters: list[str],
    layout: tuple,
) -> dict:
    """A project, its claim, its root, its five subfolders and its involvements.

    `characters` are written as `PROJ#<id>` / `CHAR#<id>` rows rather than as a
    list on the record, which is what makes the reverse question answerable: read
    forwards it is "who is in this project", and read backwards on `by-sk` it is
    "which projects involve this character" — a question with no answer today at
    any price.
    """
    parent = _folder_node(parent_id)
    if parent["lib"] != lib:
        raise ValidationError("a project is created in its own library")

    proj_id = _mint(ENTITY_PROJECT)
    now = _now()
    root, tree = _tree_steps(parent, slug, proj_id, layout)

    record = {
        "id": proj_id,
        "lib": lib,
        "slug": slug,
        "title": title or slug,
        "description": description or "",
        "rev": 1,
        "created": now,
        "updated": now,
        "root": root["node_id"],
        "hero": None,
        "counts": {"runs": 0, "scenes": 0, "movies": 0},
    }

    taken = ConflictError(f"a project called '{slug}' already exists")
    _write(
        [
            (
                _put(_lib_pk(lib), _claim_sk(ENTITY_PROJECT, slug),
                     {"entity": proj_id, "created": now}, unique=True),
                taken,
            ),
            (_put(_entity_pk(ENTITY_PROJECT, proj_id), META, record, unique=True), taken),
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


def rename_steps(kind: str, record: dict, slug: str, now: str) -> list:
    """Drop the old claim, take the new one, and rename the root folder.

    **Four writes and zero objects.** No record anywhere is rewritten, every node
    keeps its id, and the `REF#` rows, the run bindings and the `default_set` that
    all name node ids are untouched — which is the single largest simplification
    the entity model buys and the reason `domain/rewrite.py` stops existing.

    The root folder is renamed too, because a person browsing the tree should see
    the name they just chose. That it is *only* a display name is the point: the
    character is `char-…` and always was.
    """
    root = node(record["root"])
    renamed = {**root, "name": slug, "updated_at": now}
    return [
        (_delete(_lib_pk(record["lib"]), _claim_sk(kind, record["slug"])), None),
        (
            _put(_lib_pk(record["lib"]), _claim_sk(kind, slug),
                 {"entity": record["id"], "created": now}, unique=True),
            ConflictError(f"a {kind} called '{slug}' already exists"),
        ),
        (_delete_name(parent_id=root["parent_id"], name=root["name"]), None),
        (
            _put_name(renamed, parent_id=root["parent_id"], name=slug),
            ConflictError(f"'{slug}' already exists here"),
        ),
        (
            _update_meta(root["node_id"], {"name": slug, "updated_at": now}),
            NotFoundError(root["node_id"]),
        ),
    ]


def update_entity(
    kind: str, record: dict, rev: int, assignments: dict, *, slug: str | None = None
) -> dict:
    """Change an entity's attributes, and its slug, under one `rev`.

    **A stale `rev` is a 409 and never a silent overwrite.** Two people editing
    one profile is the case this exists for: the second save is refused with the
    numbers in the message, and the client re-reads rather than losing the
    first's work.

    A slug change rides in the same transaction as the attribute change, so a
    rename that collides leaves the display name unchanged too — the request
    either happened or did not.
    """
    now = _now()
    assignments = {**assignments, "rev": rev + 1, "updated": now}
    if slug is not None and slug != record["slug"]:
        assignments["slug"] = slug

    steps = [(_revised(kind, record["id"], assignments, rev), _stale(kind, rev))]
    if slug is not None and slug != record["slug"]:
        steps += rename_steps(kind, record, slug, now)

    _write(steps)
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
    child is gone before the project that lists it, exactly as `delete_node`
    deletes a subtree deepest-first. What a crash leaves is a project holding
    fewer children — visible, and finished by running this again.

    The kind order matters for the same reason one level down: a movie names
    scenes and a scene names runs, so taking them in that order never leaves a
    record pointing at something already deleted.

    The alternative this replaces was `?force=1`, which deleted the project and
    left every run's envelope naming a project id that no longer existed. That
    is the one state the model cannot repair from, and it was the only thing on
    offer for "delete this project and its work".
    """
    blob_keys: list[str] = []
    removed = collections.Counter()
    for kind in (ENTITY_MOVIE, ENTITY_SCENE, ENTITY_RUN):
        for row in project_entities(record["id"], kind):
            child = entity(kind, row["id"])
            result = delete_entity(kind, child, delete_files=delete_files)
            blob_keys.extend(result["blob_keys"])
            removed[kind] += 1
    result = delete_entity(ENTITY_PROJECT, record, delete_files=delete_files)
    blob_keys.extend(result["blob_keys"])
    logger.info("Cascade-deleted project %s (%s)", record["id"], dict(removed))
    return {"id": record["id"], "blob_keys": blob_keys, "removed": dict(removed)}


def delete_entity(kind: str, record: dict, *, delete_files: bool) -> dict:
    """Remove an entity, its claim, its links and — if asked — its folder.

    **Files are kept by default and the folder is orphaned into the library
    root.** The reverse default loses media to a typo, and there is no undo for
    an S3 delete this service can perform. `?files=delete` is the explicit
    request, and it is the only path that passes `allow_entities` to
    `delete_node`.

    **The record goes before the tree, and that order is the recoverable one.**
    What survives an interruption is a folder nothing claims — visible, movable,
    deletable by hand — rather than a record naming a node that is gone, which is
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
    if kind in CLAIM_PREFIX:
        steps.append((_delete(_lib_pk(record["lib"]), _claim_sk(kind, record["slug"])), None))
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
    if root_id:
        if delete_files:
            blob_keys = delete_node(root_id, allow_entities=True)["blob_keys"]
        else:
            _orphan(root_id, record["lib"])

    logger.info("Deleted %s %s (files %s)", kind, record["id"],
                "deleted" if delete_files else "kept")
    return {"id": record["id"], "blob_keys": blob_keys}


def _orphan(node_id: str, lib: str) -> None:
    """Cut a folder loose from the entity that owned it.

    The reverse pointer goes first, because a folder still carrying `entity`
    after its record is gone is what `delete_node` refuses and what `owner_of`
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
# **This is what kills filename magic.** Order is an attribute, not a trailing
# number in a basename, so `curate renumber` has nothing left to maintain. Group
# is an attribute, so `curate regroup` is one write and moves no objects. A
# description is one row, so two descriptions written at once stop fighting over
# one YAML document. A reference image can be called anything, and renaming it
# changes nothing here, because the row names its **node id**.

# `order` is gapped so that inserting between two entries is one write and a
# reorder never touches its neighbours. A thousand leaves ten insertions between
# any adjacent pair before the midpoints run out, and the arithmetic below falls
# back to appending when they do.
ORDER_GAP = 1000

REFERENCE_PREFIX = "REF#"


def references(char_id: str) -> list[dict]:
    """Every reference entry for one character, in `(group, order)` order.

    One query on `CHAR#<id>` — the whole reference index, which used to be a
    listing of four folders plus a parse of the bible's `references:` map, and
    which went out of step with itself whenever the two were written apart.
    """
    items = _query(
        TableName=config.catalog_table(),
        KeyConditionExpression="pk = :pk AND begins_with(sk, :ref)",
        ExpressionAttributeValues={
            ":pk": {"S": _entity_pk(ENTITY_CHARACTER, char_id)},
            ":ref": {"S": REFERENCE_PREFIX},
        },
    )
    entries = []
    for item in items:
        entry = _entity(item)
        entry["node"] = _deserialize(item["sk"])[len(REFERENCE_PREFIX) :]
        entries.append(entry)
    entries.sort(key=lambda entry: (entry.get("group") or "", entry.get("order") or 0))
    return entries


def _order_after(entries: list[dict], group: str, after: str | None) -> int:
    """Where a new entry lands: after one neighbour, or at the end of its group.

    `after` picks the midpoint between the named entry and the one following it
    in the same group, so one write places an image between two others and the
    neighbours are not touched. With no room left between them — ten insertions
    into one gap — it falls through to appending, which is a visible reordering
    rather than a silent collision on one `order` value.
    """
    in_group = [entry for entry in entries if entry.get("group") == group]
    orders = [entry.get("order") or 0 for entry in in_group]

    if after:
        for index, entry in enumerate(in_group):
            if entry["node"] != after:
                continue
            low = entry.get("order") or 0
            high = orders[index + 1] if index + 1 < len(orders) else low + 2 * ORDER_GAP
            midpoint = (low + high) // 2
            if midpoint > low:
                return midpoint
            break

    return (max(orders) if orders else 0) + ORDER_GAP


def _reference_item(char_id: str, lib: str, node_id: str, entry: dict, now: str) -> dict:
    return _put(
        _entity_pk(ENTITY_CHARACTER, char_id),
        f"{REFERENCE_PREFIX}{node_id}",
        {
            "lib": lib,
            "group": entry.get("group"),
            "order": entry.get("order"),
            "description": entry.get("description"),
            "tags": entry.get("tags"),
            "created": entry.get("created") or now,
        },
    )


def attach_reference(
    char_id: str,
    lib: str,
    node_id: str,
    *,
    group: str,
    description: str | None,
    tags: list | None,
    after: str | None,
) -> dict:
    """Mark one existing node as identity. One row, no bytes, no move.

    **The node is not copied and is not required to live anywhere in
    particular.** Reference-ness is this row and nothing else — which is the
    coupling the whole entity model removes, and the reason `reference/` stopped
    being load-bearing.

    Already-attached is a 409 rather than an overwrite, because "attach" and
    "describe" are different requests: the second is `PATCH` on the same address
    and does not reset a group somebody has already chosen.
    """
    existing = references(char_id)
    if any(entry["node"] == node_id for entry in existing):
        raise ConflictError(f"{node_id} is already a reference")

    now = _now()
    entry = {
        "node": node_id,
        "group": group,
        "order": _order_after(existing, group, after),
        "created": now,
    }
    # The row is the relationship; the words are the picture's. Both in one
    # transaction so an attach that came with a caption never half-lands.
    steps = [(_reference_item(char_id, lib, node_id, entry, now), None)]
    described = _describe_step(node_id, {"description": description, "tags": tags}, now)
    if described:
        steps.append(described)
    _write(steps)
    return entry


def update_reference(char_id: str, lib: str, node_id: str, changes: dict) -> dict:
    """Regroup, redescribe, retag or reorder one entry. One write, no objects.

    Read-then-write rather than a bare update, because `after` is a position
    relative to entries this row does not know about — and because the merge has
    to preserve the fields the request left out. The read is one query the caller
    would have made anyway to render the result.
    """
    existing = references(char_id)
    entry = next((item for item in existing if item["node"] == node_id), None)
    if entry is None:
        raise NotFoundError(node_id)

    merged = {**entry}
    if "group" in changes:
        merged["group"] = changes["group"]
    if "order" in changes:
        merged["order"] = changes["order"]
    if changes.get("after") is not None or ("group" in changes and "order" not in changes):
        merged["order"] = _order_after(
            [item for item in existing if item["node"] != node_id],
            merged.get("group"),
            changes.get("after"),
        )

    now = _now()
    steps = [(_reference_item(char_id, lib, node_id, merged, now), None)]
    described = _describe_step(node_id, changes, now)
    if described:
        steps.append(described)
    _write(steps)
    return merged


def put_references(char_id: str, lib: str, entries: list[dict]) -> list[dict]:
    """Describe or reorder many entries in one transaction.

    This is `describe-refs` and `sync-refs`, and the transaction is the point:
    twelve descriptions used to be twelve rewrites of one YAML document, each
    reading an `updated_at` and refusing if it had moved, so writing them
    concurrently was a conflict dance rather than a write.

    Order defaults to declaration order within a group, gapped, so a caller that
    sends a list gets that list back in that order without computing anything.
    """
    now = _now()
    counters: dict[str, int] = {}
    written = []
    steps = []
    for entry in entries:
        group = entry.get("group")
        counters[group] = counters.get(group, 0) + ORDER_GAP
        merged = {"node": entry["node"], "group": group,
                  "order": entry.get("order") or counters[group], "created": now}
        written.append(merged)
        steps.append((_reference_item(char_id, lib, entry["node"], merged, now), None))
        # Two rows per entry now — the set's half and the picture's — so a
        # twelve-image describe is 24 items and still one transaction per chunk.
        described = _describe_step(entry["node"], entry, now)
        if described:
            steps.append(described)

    for start in range(0, len(steps), TRANSACTION_ITEMS):
        _write(steps[start : start + TRANSACTION_ITEMS])
    return written


def detach_reference(char_id: str, node_id: str, record: dict | None = None) -> dict | None:
    """Stop calling a node identity. **The file stays exactly where it is.**

    **And it leaves the default set, in the same transaction.** That is the whole
    of this change and it is repairing a real failure: `default_set` is a list of
    node ids on the record, detaching only deleted the `REF#` row, and the
    selection route then filtered the survivors — so a re-shot reference left a
    stale id behind and a default shoot silently sent five images where seven
    were meant. Measured on the production library: four of one character's seven
    were ids nothing pointed at any more, and nothing anywhere said so.

    Two writes rather than one, and they have to be atomic: a detach that removed
    the row and failed to update the record would leave exactly the state this
    exists to prevent.

    Returns the record with the pruned list when it pruned one, so the caller can
    report it, and `None` when the set did not mention the node.
    """
    steps = [(_delete(_entity_pk(ENTITY_CHARACTER, char_id), f"{REFERENCE_PREFIX}{node_id}"), None)]

    record = record or entity(ENTITY_CHARACTER, char_id)
    current = record.get("default_set") or []
    pruned = [each for each in current if each != node_id]
    if len(pruned) != len(current):
        # `rev` is deliberately NOT bumped and NOT compared. This is a
        # consequence of a delete rather than an edit somebody made against a
        # revision they had read, and refusing the detach because a form was open
        # elsewhere would leave the row gone and the set stale — the worse half.
        steps.append((_update(
            {"pk": {"S": _entity_pk(ENTITY_CHARACTER, char_id)}, "sk": {"S": META}},
            {"default_set": pruned, "updated": _now()},
        ), None))

    _write(steps)
    return {**record, "default_set": pruned} if len(pruned) != len(current) else None


def set_project_characters(project_id: str, lib: str, characters: list[str]) -> list[str]:
    """Replace a project's involvement links.

    A replace rather than an add, because the SPA edits a set and the CLI's
    `projects link` reads the set first — an add-only endpoint would need a
    remove beside it and a client that got the difference wrong would accumulate
    links nothing removes.
    """
    now = _now()
    current = set(links(project_id, ENTITY_CHARACTER))
    wanted = list(dict.fromkeys(characters))

    steps = [
        (
            _put(_entity_pk(ENTITY_PROJECT, project_id),
                 f"{ENTITY_KEYS[ENTITY_CHARACTER][1]}{char_id}",
                 {"lib": lib, "created": now}),
            None,
        )
        for char_id in wanted
    ]
    steps += [
        (
            _delete(_entity_pk(ENTITY_PROJECT, project_id),
                    f"{ENTITY_KEYS[ENTITY_CHARACTER][1]}{char_id}"),
            None,
        )
        for char_id in current - set(wanted)
    ]

    for start in range(0, len(steps), TRANSACTION_ITEMS):
        _write(steps[start : start + TRANSACTION_ITEMS])
    return wanted


# ──────────────────── runs, scenes and movies ────────────────────
#
# The three kinds a project holds. All of them are an **envelope**: the fields
# studio owns, validates and queries, beside a payload it stores and never
# decodes.
#
# | Studio owns (row, validated, queryable) | The provider owns (blob, verbatim) |
# |---|---|
# | id, project, status, model, engine, kind, characters, bindings (node ids), timings, prediction id, error, outputs, lineage | the exact `input` sent, the exact response returned |
#
# That split preserves the reason the old rule existed — the pipeline changes the
# payload's shape freely, so a service that parsed one would become a liar — while
# giving the app a run it can render. `docs/WEB_APP.md`'s "never decode
# request.json" survives, moved to where it is actually true.
#
# **The listing row is a projection and the only one in this module.** A project's
# runs are `pk = PROJ#<id>, begins_with(sk, "RUN#"), ScanIndexForward=false` —
# real pagination, newest first — and the row carries status, model, kind and a
# thumbnail so the grid draws without a `BatchGetItem` over hundreds of
# envelopes. It is safe to project *because a run is immutable once it
# completes*: there is nothing left to keep in step. Do not copy this reasoning
# onto a slug claim, where the opposite is true.


def _listing_sk(kind: str, created: str, entity_id: str) -> str:
    """`RUN#<created>#<run_id>` — sortable, unique, and newest-last by string.

    The timestamp comes first so the range is chronological, and the id follows
    so two entities created in the same microsecond are still two rows. The
    reverse order a listing wants is `ScanIndexForward=False` rather than an
    inverted key, because the same rows are also read oldest-first by anything
    replaying a project.
    """
    return f"{ENTITY_KEYS[kind][1]}{created}#{entity_id}"


def create_project_entity(
    kind: str,
    lib: str,
    project_id: str,
    parent_id: str,
    *,
    slug: str | None,
    attributes: dict,
    listing: dict,
    subfolders: tuple = (),
) -> dict:
    """A run, a scene or a movie: envelope, listing row, folder — one write.

    **Its folder is named for the slug and its record names the folder's node
    id**, which is why renaming or moving that folder afterwards strands nothing.
    That is the property the timestamp-slug folder name used to carry and could
    not keep: a run that recorded a path was stranded by the first rename above
    it, and `domain/rewrite.py` existed for exactly that.

    **`slug=None` means the entity has no label, and its folder is named for its
    id.** That is a RUN. A scene and a movie are things a person plans and comes
    back to, so both keep a slug and a title; a run is a machine event and has
    neither. Its old slug was `<timestamp>_<hint>`, which made it unique only by
    embedding `created` — a column already on the row and already what sorting
    and `--since` read — while the hint alone collided across runs. Nothing keyed
    on it, no claim row enforced it, and resolving one needed an exact match, a
    substring fallback and an ambiguity error to prop it up.

    The character usage rows go in the same transaction, because "which runs used
    this character" has to be true the moment the run exists — a link written
    afterwards is a link a crash can lose.
    """
    parent = _folder_node(parent_id)
    entity_id = _mint(kind)
    now = _now()

    folder = _new_node(parent, slug or entity_id, KIND_FOLDER, entity=entity_id)
    steps = _node_steps(folder)
    for name in subfolders:
        steps += _node_steps(_new_node(folder, name, KIND_FOLDER))

    record = {
        "id": entity_id,
        "lib": lib,
        "project": project_id,
        **({"slug": slug} if slug else {}),
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
        (_bump_counts(project_id, COUNT_FIELD[kind], 1), NotFoundError(project_id)),
        *steps,
        *[
            (
                _put(_entity_pk(kind, entity_id),
                     f"{ENTITY_KEYS[ENTITY_CHARACTER][1]}{char_id}",
                     {"lib": lib, "created": now}),
                None,
            )
            for char_id in attributes.get("characters") or []
        ],
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
    kind: str, record: dict, assignments: dict, listing: dict | None = None
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
    _write(steps)
    return {**record, **{k: v for k, v in assignments.items() if v is not None}}


def runs_for_character(char_id: str) -> list[dict]:
    """Every run that used one character, as envelopes.

    `runs find --character` was a walk over every project, every run folder and
    three JSON documents each. It is `by-sk` now: one query for the ids, one
    batched read for the records.
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


# Everything a shot row holds, and it is the list of what a storyboard IS.
#
# It held four names — `order`, `prompt`, `run`, `panel` — which was the whole
# of a shot before storyboards existed. The CLI has authored `beat`, `panels`,
# `motion`, `continues` and `opens_on` since, and every one of them was dropped
# here on the way in: a seven-shot plan ingested clean, reported success, and
# came back as seven rows of `{id, order, created}`. The plan was never stored,
# so nothing could draw it and `scenes board` had nothing to render from.
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


def put_shots(scene_id: str, entries: list[dict]) -> list[dict]:
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

    for start in range(0, len(steps), TRANSACTION_ITEMS):
        _write(steps[start : start + TRANSACTION_ITEMS])
    written.sort(key=lambda entry: entry.get("order") or 0)
    return written


def update_shot(scene_id: str, shot_id: str, changes: dict) -> dict:
    """One shot: which run rendered it, which panel it came from, its plan.

    The same field list as `put_shots`, because a shot patched one field at a
    time and a shot rewritten by a plan revision are the same row. They held two
    different lists once, and the narrower one silently discarded whatever the
    other had just written.
    """
    entry = next((item for item in shots(scene_id) if item["id"] == shot_id), None)
    if entry is None:
        raise NotFoundError(shot_id)

    merged = {**entry, **{k: v for k, v in changes.items() if k in SHOT_FIELDS}}
    _write([(_shot_item(scene_id, shot_id, merged), None)])
    return merged


# ─────────────────────────── the phrasebook ───────────────────────────
#
# A per-model list of avoid/use pairs — a table wearing a YAML file, and it is a
# table now. `phrasebook add` stops being able to fail on a library that has
# never held the document, because there is no document.


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


def add_term(lib: str, model: str, avoid: str, use: str, note: str | None = None) -> dict:
    """Claim one avoid/use pair. A duplicate is a 409, not an overwrite.

    Conditional, for the reason every claim here is: the pair *is* the key, so
    "already there" is a condition failure rather than a read somebody raced.
    """
    now = _now()
    record = {"model": model, "avoid": avoid, "use": use, "note": note, "created": now}
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
