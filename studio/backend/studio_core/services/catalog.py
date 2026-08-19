"""The catalog: libraries, nodes, and every write that changes one.

**This is the only module that knows the table's item shapes.** Everything above
it — routes, and the services that will grow beside them — deals in node records
and library ids, never in a `pk`, an `sk` or a `NAME#` prefix. That boundary is
the point of the module rather than tidiness: the two-item-per-node layout below
is a consequence of wanting list-by-parent *and* unique-name-per-folder out of
one table, and it must not leak into a route handler that would then have to be
rewritten if the layout ever changed.

## What is in the table

```
Library   lib-<uuid>     the sharing unit; has members
 └ Node   node-<uuid>    a folder or a file, with a parent pointer
```

One node type. A folder is a node with no blob; a file is a node with one.

| Item | `pk` | `sk` |
|---|---|---|
| Library | `LIB#<lib_id>` | `META` |
| Membership | `USER#<sub>` | `LIB#<lib_id>` |
| Node — by parent | `NODE#<parent_id>` | `NAME#<name>` |
| Node — by id | `NODE#<node_id>` | `META` |

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
  why it is written first — see `move_node`.
* **`blob_key` is opaque.** Nothing here parses it, derives it, or assumes a
  shape. Prod holds `characters/<slug>/…` and `projects/<slug>/…` keys written
  years before this table existed alongside `blobs/<node_id>` keys written after
  it, and both are correct forever precisely because the text carries no
  meaning. A function here that split a `blob_key` on `/` would re-create the
  coupling the catalog was built to remove.

## The library root is an ordinary node

`root_node` on the library names a real `NODE#<id>`/`META` row, with `path`
`"/"` and **no** `parent_id`. #280 does not say so either way; the alternative —
a root that is only an id on the library item — means every function that needs
a parent's `path` has a special case for "the parent is the root", and
`create_node` would have to read the library to find out. A root that is a node
costs one row and removes that branch everywhere.

Its missing `parent_id` is then load-bearing: it is what makes "rename the
library root", "move it" and "delete it" refuse, since there is no `NAME#` item
to rewrite. That is the same refusal `keys.assert_inside_root` makes on the S3
side, arrived at from the data rather than from a string comparison.

## What this module does not do

It never touches S3. `delete_node` returns the `blob_key` values it removed
rows for rather than deleting the objects behind them, because two nodes may
point at one key — a copy in this model copies a row, not bytes — so whether a
blob is now unreferenced is not a question a single delete can answer.
"""

import logging
import time
import uuid
from datetime import datetime, timezone

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

# `by-sk` inverts the table so an sk can be asked who points at it; the only
# question this module asks it is "who is in library X". `by-path` is the
# subtree index: hashed on `lib`, ranged on `path`, so one `begins_with` reads a
# whole branch. The third GSI, `by-recent`, is for the reel and has no caller
# here yet, which is why it is not named.
BY_SK_INDEX = "by-sk"
BY_PATH_INDEX = "by-path"

# The sort key of the record half of a node, and of a library.
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

_serialize = TypeSerializer().serialize
_deserialize = TypeDeserializer().deserialize


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


def _lib_sk(lib: str) -> str:
    return f"LIB#{lib}"


def _lib_pk(lib: str) -> str:
    """The library's own partition — the same text as `_lib_sk`, spelled apart.

    That the two agree is the mechanism rather than a coincidence: a membership
    is filed under the *user* and carries `LIB#<id>` as its sort key, so the
    inverted index reaches every member of a library by asking for the string
    the library itself is keyed on. Collapsing them into one helper would make a
    reader think one of the two callers had the wrong key.
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


def _query(**kwargs) -> list[dict]:
    """Every page of one query, as raw items.

    Paginated rather than single-shot because DynamoDB's 1 MB page is measured
    in bytes read, not items returned: a filtered query can come back empty with
    a `LastEvaluatedKey` still set, and code that trusted the first page would
    report an empty folder for a full one.
    """
    items: list[dict] = []
    try:
        for page in dynamodb.client().get_paginator("query").paginate(**kwargs):
            items.extend(page.get("Items", []))
    except ClientError as exc:
        logger.warning("Query failed (%s): %s", kwargs.get("IndexName", "table"), exc)
        raise UpstreamError("Could not read the catalog") from exc
    return items


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


def members_of(lib: str) -> list[dict]:
    """Everyone with access to one library.

    The reverse of `libraries_for`, and the reason `by-sk` exists: membership is
    stored under the *user's* partition so a sign-in reads one partition, which
    leaves "who else is in here" with nothing to query but the inverted index.
    """
    items = _query(
        TableName=config.catalog_table(),
        IndexName=BY_SK_INDEX,
        KeyConditionExpression="sk = :sk",
        ExpressionAttributeValues={":sk": {"S": _lib_sk(lib)}},
    )
    rows = [_attributes(item) for item in items]
    return [
        {
            "sub": row["pk"].split("#", 1)[1],
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


def subtree(lib: str, path: str) -> list[dict]:
    """Every node beneath a path, as full records — refusing rather than truncating.

    One `begins_with` on `by-path` reads a whole branch, which is what the
    materialised `path` is for. Pass `child_path(record)` to get a node's
    descendants; the node itself is not among them, because its own `path` names
    its ancestors and stops short.

    **The by-parent items are filtered out here.** They sit in this index too —
    #280 puts `lib` and `path` on both halves of a node — so an unfiltered query
    returns every node twice, once complete and once as a projection. `META` is
    the half that is the record.

    **The cap is a refusal, not a limit**, and that is inherited deliberately
    from `manage._subtree`. Both callers of this function are writes: a move
    rewrites every descendant's `path` and a delete removes every descendant's
    rows. A truncated answer to either is the setup for doing half the job and
    reporting success.
    """
    cap = config.max_folder_objects()
    items = _query(
        TableName=config.catalog_table(),
        IndexName=BY_PATH_INDEX,
        KeyConditionExpression="lib = :lib AND begins_with(#path, :path)",
        ExpressionAttributeNames={"#path": "path"},
        ExpressionAttributeValues={":lib": {"S": lib}, ":path": {"S": path}},
    )
    records = [_record(item) for item in items if _deserialize(item["sk"]) == META]
    if len(records) > cap:
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
    values = {f":{index}": _serialize(value) for index, value in enumerate(assignments.values())}
    return {
        "Update": {
            "TableName": config.catalog_table(),
            "Key": key,
            "UpdateExpression": "SET " + ", ".join(f"{k} = :{k[1:]}" for k in names),
            "ExpressionAttributeNames": names,
            "ExpressionAttributeValues": values,
            "ConditionExpression": "attribute_exists(pk)",
        }
    }


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


def create_node(
    parent_id: str,
    raw_name: str | None,
    kind: str,
    *,
    blob_key: str | None = None,
    size: int | None = None,
    content_type: str | None = None,
) -> dict:
    """Add a folder or a file under an existing parent.

    **The library is read off the parent rather than passed in.** A `lib`
    argument would be a second source of truth for the one attribute every GSI
    partitions on, and a caller that got it wrong would produce a node that is
    listed in one library's subtree and owned by another. The parent already
    knows, so it is asked.

    `blob_key` is required for a file and refused for a folder, which is the
    whole of the distinction: #280 defines a folder as a node with no blob. Size
    and content type are optional because the caller writing the object may not
    know either yet — `set_blob` fills them in later.
    """
    if kind not in KINDS:
        raise ValidationError(f"kind must be one of {', '.join(sorted(KINDS))}")
    if kind == KIND_FILE and not blob_key:
        raise ValidationError("a file needs a blob_key")
    if kind == KIND_FOLDER and blob_key:
        raise ValidationError("a folder cannot carry a blob_key")

    name = keys.clean_name(raw_name)
    parent = _folder_node(parent_id)
    now = _now()

    record = {
        "node_id": f"node-{uuid.uuid4()}",
        "parent_id": parent_id,
        "lib": parent["lib"],
        "name": name,
        "kind": kind,
        "blob_key": blob_key,
        "size": size,
        "content_type": content_type,
        "path": child_path(parent),
        "created_at": now,
        "updated_at": now,
    }

    _write(
        [
            (
                _put_name(record, parent_id=parent_id, name=name),
                ConflictError(f"'{name}' already exists here"),
            ),
            (
                {
                    "Put": {
                        "TableName": config.catalog_table(),
                        "Item": _item(
                            {"pk": _node_pk(record["node_id"]), "sk": META, **record}
                        ),
                        # A v4 UUID cannot realistically collide, so this guard
                        # never fires — it is here so that no put in this module
                        # is capable of overwriting a record, which is the
                        # property worth being able to state without exceptions.
                        "ConditionExpression": "attribute_not_exists(pk)",
                    }
                },
                ConflictError(f"'{name}' already exists here"),
            ),
        ]
    )

    logger.info("Created %s %s under %s", kind, record["node_id"], parent_id)
    return {key: value for key, value in record.items() if value is not None}


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

    _write(
        [
            (_delete_name(parent_id=parent_id, name=record["name"]), None),
            (
                _put_name(updated, parent_id=parent_id, name=name),
                ConflictError(f"'{name}' already exists here"),
            ),
            (_update_meta(node_id, {"name": name, "updated_at": now}), NotFoundError(node_id)),
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
    merging two trees. Crossing libraries is refused as well — a transfer
    rewrites `lib` across the branch and is a different operation.
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

    _rewrite_paths(descendants, old=branch, new=child_path(moved))

    logger.info("Moved %s under %s (%d descendants)", node_id, parent_id, len(descendants))
    return {**moved, "moved": True, "descendants": len(descendants)}


def _rewrite_paths(descendants: list[dict], *, old: str, new: str) -> None:
    """Re-materialise `path` on a moved branch, both halves of every node.

    The by-parent item carries `path` too, so each descendant costs two writes —
    which is what fixes the batch at fifty nodes. Only the prefix changes: the
    part of a descendant's path below the moved node describes ancestors that
    moved with it and is copied across untouched.
    """
    steps: list[tuple[dict, Exception | None]] = []
    for record in descendants:
        path = new + record["path"][len(old):]
        steps.append(
            (
                _update_meta(record["node_id"], {"path": path, "updated_at": _now()}),
                NotFoundError(record["node_id"]),
            )
        )
        steps.append(
            (
                _update_name(
                    parent_id=record["parent_id"],
                    name=record["name"],
                    assignments={"path": path},
                ),
                NotFoundError(record["node_id"]),
            )
        )

    for start in range(0, len(steps), TRANSACTION_ITEMS):
        _write(steps[start : start + TRANSACTION_ITEMS])


def delete_node(node_id: str) -> dict:
    """Remove a node and everything beneath it, and report the blobs it held.

    **Deepest first, the node itself last.** Batching means a subtree bigger
    than fifty nodes is several transactions, so an interruption is possible;
    deleting upwards means what survives is still a tree hanging off a parent
    that lists it, rather than a set of rows nothing can reach. Re-running the
    delete finishes the job.

    Nothing in S3 is touched. The `blob_key` values come back so the caller can
    decide what to do about the bytes — two nodes may point at one key, since a
    copy in this model copies a row, so "is this blob now unreferenced" is not a
    question one delete can answer.
    """
    record = node(node_id)
    if not record.get("parent_id"):
        raise ValidationError("the library root cannot be deleted")

    descendants = subtree(record["lib"], child_path(record))
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
