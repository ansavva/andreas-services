"""Creating, renaming, moving, copying, deleting and editing things in a library.

Everything destructive in studio lives here, in one module, on purpose: the read
paths in `browse` are allowed to be forgiving — a missing folder is an empty
listing — and nothing in here is. A write that cannot be described exactly is
refused.

**These are catalog writes now** (#316, #317, #319), and three of the four rules
this file used to open with were consequences of S3 rather than decisions:

* **Nothing overwrites, and a condition expression is what says so.** S3 has no
  conditional put, so every create and rename read its destination first and
  raced whoever else was writing. `services.catalog` puts its `NAME#` item under
  `attribute_not_exists(pk)` and turns the cancelled transaction into the 409 the
  API already returned. The window is gone, not narrowed.
* **A folder is a row.** `create_folder` writes no zero-byte marker, because
  there is no longer anything for one to fake, and the last reader that had to
  skip one went with it.
* **A rename and a move copy no bytes at all.** Both were `CopyObject` per key
  plus a delete; both are one transaction now, and a folder move rewrites its
  descendants' `path` in batches `services.catalog` bounds.

What did *not* change is the rule that was never about storage:

* **Names are validated, never repaired.** `keys.clean_name` rejects a slash
  rather than escaping it, because "rename" and "move" are different requests and
  punctuation must not silently turn one into the other. Move is a separate pair
  of functions below and takes a *destination folder* rather than a name, so the
  two requests stay distinguishable all the way down.
* **Scope is bounded before it is applied.** `catalog.subtree` refuses past
  `config.max_folder_objects` rather than starting work the Lambda's clock will
  interrupt. It is the same refusal the `walk_all` count here used to make, moved
  and made about rows — and it is still a refusal rather than a limit, because a
  truncated answer to a move or a delete is the setup for doing half the job and
  reporting success.

`config.max_bulk_keys` is the one bound that did **not** survive the translation
intact: it is 1000 because `DeleteObjects` takes 1000 keys per call, and a bulk
delete is no longer one call. See `_bulk`.

## What still touches S3, and in which order

Only bytes. `copy_objects` issues one `CopyObject` per blob, the two deletes
remove blobs **after** their rows, and `update_text` overwrites one object.
Nothing here lists the bucket any more.

The delete order is the recoverable one and is worth stating where it is
implemented: an orphan blob is invisible to every reader and collectable later,
while a row pointing at a blob that is gone is a broken tile in the grid. If the
second half fails, what is left is the harmless kind of inconsistent.

## Addresses

Every function here takes a slash-joined **name path** — the same address
`GET /api/tree?prefix=` accepts and the same string a listing hands back as
`key`. It is not an S3 key and is never used as one: `_walk` resolves it against
the catalog, one `NAME#` lookup per segment, and everything below deals in node
ids. For material written before the catalog the two strings happen to be equal,
which is what let the read path move first; nothing here may assume it.

`lib` is `g.library`, resolved and membership-checked once per request by
`app_factory.resolve_caller`. Nothing here checks membership again, for
`/api/resolve`'s reason: the walk starts at that library's root and every step is
a child of the step before it, so a node reached this way is in that library or
the walk would not have reached it.

**The library root refuses to be renamed, moved or deleted because it has no
`parent_id`** — there is no `NAME#` item to rewrite — which is the same refusal
`keys.assert_inside_root` made from a string comparison, arrived at from the data
instead.
"""

import logging

from studio_core import config
from studio_core.clients.aws import s3
from studio_core.errors import ConflictError, NotFoundError, ValidationError
from studio_core.services import catalog, keys

logger = logging.getLogger(__name__)

# How many `name (n).ext` variants one name may spawn in a destination before the
# request is refused. Generous — copying the same clip into one folder twice is
# ordinary — but finite, so a script cannot fill a folder with numbered copies.
MAX_COPY_VARIANTS = 100


# ─────────────────────────── name paths to nodes ───────────────────────────


def _walk(lib: str, raw_path: str | None) -> tuple[dict, list[str]]:
    """The node a name path names, and the names walked to reach it.

    The names come back as well as the record because every response here echoes
    a path, and the walked list is the *normalised* one — empty segments and a
    missing trailing slash are gone by construction. Echoing the request instead
    would let two spellings of one folder answer with two different `prefix`
    values, which is the mistake `browse.list_folder` avoids by reading its
    prefix back off the breadcrumbs.

    A missing segment is re-raised naming everything walked so far, so the 404
    says which segment was the first one absent rather than only which name was.

    No traversal rules and no root confinement, and neither is missing: each
    segment is looked up as an exact `NAME#` sort key and `keys.clean_name`
    refuses a slash, a `.`, a `..` and a control character on the way *in*, so
    `../elsewhere` is simply a name nothing is called.
    """
    node_id = catalog.library(lib)["root_node"]
    walked: list[str] = []
    for name in [segment for segment in (raw_path or "").split("/") if segment]:
        walked.append(name)
        try:
            node_id = catalog.child_by_name(node_id, name)["node_id"]
        except NotFoundError as error:
            raise NotFoundError("/".join(walked)) from error
    return catalog.node(node_id), walked


def _as_prefix(names: list[str]) -> str:
    """A walked path back as a folder prefix. The root is the empty string."""
    return "".join(f"{name}/" for name in names)


def _folder_at(lib: str, raw_path: str | None) -> tuple[dict, list[str]]:
    """The folder a name path names.

    The kind check is what keeps the folder verbs and the object verbs apart at
    the service boundary, where the API keeps them apart at the route boundary.
    Without it `PATCH /api/folder` would rename a file and answer with a `prefix`
    naming something that is not one.
    """
    record, walked = _walk(lib, raw_path)
    if record["kind"] != catalog.KIND_FOLDER:
        raise ValidationError(f"'{record['name']}' is a file, not a folder")
    return record, walked


def _file_at(lib: str, raw_path: str | None) -> tuple[dict, list[str]]:
    """The file a name path names. The mirror of `_folder_at`, same reason."""
    record, walked = _walk(lib, raw_path)
    if record["kind"] != catalog.KIND_FILE:
        raise ValidationError(f"'{record['name']}' is a folder, not a file")
    return record, walked


def _bulk(raw_keys: list | None, verb: str) -> None:
    """Refuse a selection that is empty or larger than one request may carry.

    **The cap now bounds a per-node cost rather than a single call**, and that is
    worth knowing before it is raised. `config.max_bulk_keys` is 1000 because
    `DeleteObjects` takes 1000 keys per call, so a bulk delete was one round
    trip; against the catalog it is a transaction per node with the blobs still
    going in one call at the end. The bound is the same number guarding a
    different quantity, which is the kind of drift that only shows up as a
    timeout.
    """
    if not isinstance(raw_keys, list) or not raw_keys:
        raise ValidationError("keys must be a non-empty list")
    cap = config.max_bulk_keys()
    if len(raw_keys) > cap:
        raise ValidationError(f"cannot {verb} more than {cap} objects in one request")


# ──────────────────────────── create and rename ────────────────────────────


def create_folder(lib: str, raw_prefix: str | None, raw_name: str | None) -> dict:
    """Create an empty folder inside `raw_prefix`.

    One transaction and **zero objects**. The zero-byte marker S3 needed to make
    an empty folder visible is gone with the listings that read it: a folder is a
    row, and a row is visible the moment it is written.

    A name already taken is `catalog.create_node`'s condition failure, not a
    listing this function did first.
    """
    parent, walked = _folder_at(lib, raw_prefix)
    record = catalog.create_node(parent["node_id"], raw_name, catalog.KIND_FOLDER)

    logger.info("Created folder %s under %s", record["name"], parent["node_id"])
    return {"prefix": f"{_as_prefix(walked)}{record['name']}/", "name": record["name"]}


def rename_object(lib: str, raw_key: str | None, raw_name: str | None) -> dict:
    """Rename one file within its own folder."""
    record, walked = _file_at(lib, raw_key)
    renamed = catalog.rename_node(record["node_id"], raw_name)

    return {
        "key": f"{_as_prefix(walked[:-1])}{renamed['name']}",
        "name": renamed["name"],
        "renamed": renamed["renamed"],
    }


def rename_folder(lib: str, raw_prefix: str | None, raw_name: str | None) -> dict:
    """Rename a folder within its own parent. Everything beneath it comes along.

    **Nothing beneath it moves, and there is nothing to count.** A prefix rename
    was a copy and a delete per key, so the old response reported how many
    objects it had rewritten; `path` names ancestors by id and a rename changes
    none of them, so the descendants are untouched rows and `objects` has been
    dropped rather than reported as zero.
    """
    record, walked = _folder_at(lib, raw_prefix)
    renamed = catalog.rename_node(record["node_id"], raw_name)

    return {
        "prefix": f"{_as_prefix(walked[:-1])}{renamed['name']}/",
        "name": renamed["name"],
        "renamed": renamed["renamed"],
    }


# ──────────────────────────────── move ────────────────────────────────


def move_objects(lib: str, raw_keys: list | None, raw_destination: str | None) -> dict:
    """Move one or many files into another folder, keeping their names.

    The counterpart of `rename_object`: that one changes the last segment and
    keeps the folder, this one changes the folder and keeps the last segment.
    Neither can do the other's job, which is the point — a caller cannot reach a
    move by putting a slash in a name, and cannot reach a rename by naming a
    destination.

    **Every destination is checked before any node moves.** Each `move_node` is
    its own transaction, so a conflict found on the eighth file would leave seven
    already moved: a selection split across two folders with nothing to say where
    the boundary fell. The check is a read, and a read is beatable — another
    writer taking the name in between still surfaces as a 409 part-way through —
    but that is the rare case the check exists to make rare, and the transaction
    is what keeps the individual move from overwriting anything.

    Files already sitting in the destination are not a conflict; they are skipped
    and counted, because "move these forty files there" is a reasonable thing to
    say when three of them are there already.
    """
    _bulk(raw_keys, "move")

    destination, walked = _folder_at(lib, raw_destination)
    prefix = _as_prefix(walked)
    # Every key resolved before any node moves: a request naming one bad key does
    # nothing at all rather than moving the good ones first and then failing.
    sources = [_file_at(lib, raw)[0] for raw in raw_keys]

    moving: list[dict] = []
    skipped = 0
    claimed: set[str] = set()

    for record in sources:
        if record["parent_id"] == destination["node_id"]:
            skipped += 1
            continue
        # Two sources with the same name would otherwise be one conflict against
        # the other, found half-way. A grid selection lives in one folder so its
        # names are already unique, but the endpoint does not require that and
        # must not depend on it.
        if record["name"] in claimed:
            raise ConflictError(f"two of these files are named '{record['name']}'")
        claimed.add(record["name"])
        moving.append(record)

    for record in moving:
        if _taken(destination["node_id"], record["name"]):
            raise ConflictError(f"'{record['name']}' already exists there")

    for record in moving:
        catalog.move_node(record["node_id"], destination["node_id"])

    logger.info(
        "Moved %d nodes to %s (%d already there)",
        len(moving),
        destination["node_id"],
        skipped,
    )
    return {
        "destination": prefix,
        "moved": len(moving),
        "skipped": skipped,
        "keys": [f"{prefix}{record['name']}" for record in moving],
    }


def _taken(parent_id: str, name: str) -> bool:
    """Whether a folder already holds this name.

    A `GetItem` on the by-parent item's own primary key, so asking costs the same
    whether the folder holds two files or two thousand. It is only ever a
    *pre*-check — the refusal that cannot be raced is `_put_name`'s condition
    expression inside the transaction, and this exists so a bulk move finds the
    conflict before it has applied any of itself.
    """
    try:
        catalog.child_by_name(parent_id, name)
    except NotFoundError:
        return False
    return True


def move_folder(lib: str, raw_prefix: str | None, raw_destination: str | None) -> dict:
    """Move a folder, and everything beneath it, under a different parent.

    Both refusals that used to be spelled here are `catalog.move_node`'s now, and
    both survive the translation because they were never really about S3. A
    folder cannot be moved into itself or beneath itself — there the copy loop
    would have read its own output as it wrote it, here the subtree would contain
    its own ancestor — and a name already taken at the destination refuses the
    whole request, because merging two trees is not something this can do safely.

    `descendants` replaces the old `objects` count and is a different number
    about a different thing: no object moves, and what the operation touched is
    the `path` on every row beneath the one that did.
    """
    record, _walked = _folder_at(lib, raw_prefix)
    destination, destination_walked = _folder_at(lib, raw_destination)
    moved = catalog.move_node(record["node_id"], destination["node_id"])

    return {
        "prefix": f"{_as_prefix(destination_walked)}{record['name']}/",
        "name": record["name"],
        "moved": moved["moved"],
        "descendants": moved["descendants"],
    }


# ──────────────────────────────── copy ────────────────────────────────


def copy_objects(lib: str, raw_keys: list | None, raw_destination: str | None) -> dict:
    """Copy one or many files into another folder, leaving the sources alone.

    **The only write in this service that copies bytes**, and that is the point
    of it rather than an oversight. Every other copy this module used to make was
    half of a rename or a move, and all of those are transactions now.

    It takes the same `{keys, destination}` as `move_objects` and differs in two
    places:

    * **Nothing is deleted.** The sources stay where they are.
    * **A name already taken at the destination is numbered, not refused.**
      `clip.mp4` arriving beside a `clip.mp4` becomes `clip (2).mp4`. A move
      refuses the whole request on a conflict because a half-done move splits a
      selection across two folders; a copy has no such split, and copying a file
      into a folder that already holds the name is the ordinary case rather than
      the edge.

    **Numbering consults names and nothing else.** An earlier version compared
    byte sizes so that re-copying an identical file was silently skipped — a copy
    quietly deciding not to copy, which is the same "has this been done already"
    bookkeeping the favourites feature was removed for. Ask for a copy, get a
    copy. Nothing is overwritten in any branch.

    **Each copy gets its own blob, and that is load-bearing rather than
    incidental.** A row is cheap and a second row on one `blob_key` would be
    cheaper still, but `catalog.delete_node` reports the keys it removed rows for
    without asking whether anything else still points at them — there is no index
    on `blob_key` — so the two deletes below would destroy a surviving copy's
    bytes. Copy-on-write is #334 and has to revisit that; until it does, the
    invariant "no two rows share a key" is held here, by the `CopyObject`.

    The row is minted before its bytes, so a failure between the two leaves a
    placeholder — a row with a key and no object — which a listing renders
    without a URL rather than as a broken tile. That is #294's state and the same
    trade `routes/nodes.record_run` makes.
    """
    _bulk(raw_keys, "copy")

    destination, walked = _folder_at(lib, raw_destination)
    prefix = _as_prefix(walked)
    sources = [_file_at(lib, raw)[0] for raw in raw_keys]

    # Every source's bytes located before any row is written, for the reason the
    # key resolution above happens first: one unreadable source must not leave
    # half a request applied.
    blobs = [(record, _source_blob(record)) for record in sources]

    # The destination's names, listed once and then kept current in memory, so a
    # bulk copy of forty costs one query rather than forty — and so two sources
    # sharing a name in one request number each other instead of both claiming
    # the same free one.
    taken = {entry["name"] for entry in catalog.children(destination["node_id"])}
    copied: list[str] = []

    for record, (blob_key, metadata) in blobs:
        name = _free_copy_name(record["name"], taken)
        taken.add(name)

        created = catalog.create_node(destination["node_id"], name, catalog.KIND_FILE)
        s3.copy(blob_key, created["blob_key"])
        catalog.set_blob(
            created["node_id"],
            created["blob_key"],
            size=metadata.get("ContentLength", 0),
            content_type=metadata.get("ContentType"),
        )
        copied.append(name)

    logger.info("Copied %d objects into %s", len(copied), destination["node_id"])
    return {
        "destination": prefix,
        "copied": len(copied),
        "keys": [f"{prefix}{name}" for name in copied],
    }


def _source_blob(record: dict) -> tuple[str, dict]:
    """Where a file's bytes are, and what S3 says about them.

    A file row with no `blob_key`, or one whose object is not there, is a
    placeholder whose upload never landed (#294). There is nothing to copy, and a
    404 naming the file is the honest answer — `s3.head` raises exactly that.

    The size and content type come from S3 rather than from the source row so the
    copy describes the bytes it actually received, not what the source claimed
    about them.
    """
    blob_key = record.get("blob_key")
    if not blob_key:
        raise NotFoundError(record["name"])
    return blob_key, s3.head(blob_key)


def _free_copy_name(name: str, taken: set[str]) -> str:
    """The first name this copy can take without overwriting anything."""
    if name not in taken:
        return name

    for attempt in range(2, MAX_COPY_VARIANTS + 1):
        candidate = keys.numbered_name(name, attempt)
        if candidate not in taken:
            return candidate

    raise ConflictError(
        f"'{name}' already names {MAX_COPY_VARIANTS} files there — "
        "rename some of them first"
    )


# ──────────────────────────────── edit ────────────────────────────────


def update_text(lib: str, raw_key: str | None, raw_content: str | None) -> dict:
    """Overwrite a text file's contents and restamp its row.

    The only write in this service that a person authors rather than the
    pipeline, and it is bounded on all four sides: the path must name a **file**
    that already has **bytes** (so this cannot create anything — studio's only
    upload is the presigned PUT in `routes/nodes`), of a **text kind** (so it
    cannot be pointed at a `.mp4`), whose new body is a **string** under
    `config.max_text_bytes`.

    **That last one is not a formality.** `browse.text_object` hands the editor a
    *truncated* copy of anything over the cap, and saving that back would delete
    the tail. The frontend refuses to open an editor on a truncated file, and the
    cap here means a file that somehow grew past it in between cannot be silently
    beheaded either.

    **The refusal that keeps "edit" from becoming "upload" moved and did not
    weaken.** It used to be `s3.exists` on the key; it is now a row that must be
    a file and must carry a blob. A folder and a placeholder are both refused,
    and both used to be unreachable only because a key naming neither existed.

    **Bytes first, then the row** — the reverse of a delete, for the same reason
    the delete is the way round it is. `size` on the row is a claim about an
    object; writing it before the object exists would be a claim about bytes that
    were never stored, and a listing reports that number without re-reading S3.
    """
    record, walked = _file_at(lib, raw_key)
    name = record["name"]

    if keys.kind(name) != "text":
        raise ValidationError("key is not an editable text file")
    if not isinstance(raw_content, str):
        raise ValidationError("content must be a string")

    body = raw_content.encode("utf-8")
    cap = config.max_text_bytes()
    if len(body) > cap:
        raise ValidationError(f"content must be smaller than {cap} bytes")

    blob_key = record.get("blob_key")
    if not blob_key:
        raise NotFoundError(name)

    content_type = keys.content_type(name)
    s3.put_text(blob_key, body, content_type)
    catalog.set_blob(record["node_id"], blob_key, size=len(body), content_type=content_type)

    logger.info("Saved %d bytes to %s", len(body), record["node_id"])
    return {
        "key": f"{_as_prefix(walked[:-1])}{name}",
        "name": name,
        "language": keys.language(name),
        "bytes": len(body),
    }


# ─────────────────────────────── delete ───────────────────────────────


def delete_objects(lib: str, raw_keys: list | None) -> dict:
    """Delete one or many files.

    Bulk and single are the same call because the grid's selection is the reason
    delete exists at all — a viewer that could only remove one file at a time
    would not be worth the write permission this endpoint needs.

    **Every row goes before any blob does**, and the blobs go in one call at the
    end rather than one per file. The order is the recoverable one: an orphan
    blob is invisible to every reader and collectable later, while a row pointing
    at a blob that is gone is a broken tile the user sees. `studio catalog gc`
    (#318) is what collects the orphans, and it exists because this order
    produces them on purpose.

    **One name is resolved once.** Two spellings of one file in a selection used
    to be two `DeleteObject`s on the same key, which S3 treats as idempotent; a
    row deleted twice is a 404 raised after the first half of the request already
    applied. Deduplicating on the node id keeps "resolve everything, then delete"
    true for a selection that names something twice.
    """
    _bulk(raw_keys, "delete")

    # Every key resolved before any row is deleted: a request that names one bad
    # key does nothing at all rather than deleting the good ones first.
    resolved: list[tuple[dict, list[str]]] = []
    seen: set[str] = set()
    for raw in raw_keys:
        record, walked = _file_at(lib, raw)
        if record["node_id"] in seen:
            continue
        seen.add(record["node_id"])
        resolved.append((record, walked))

    blob_keys: list[str] = []
    for record, _walked in resolved:
        blob_keys.extend(catalog.delete_node(record["node_id"])["blob_keys"])
    s3.delete(blob_keys)

    logger.info("Deleted %d nodes and %d blobs", len(resolved), len(blob_keys))
    return {
        "deleted": len(resolved),
        "keys": [f"{_as_prefix(walked[:-1])}{record['name']}" for record, walked in resolved],
    }


def delete_folder(lib: str, raw_prefix: str | None) -> dict:
    """Delete a folder and everything beneath it.

    `deleted` counts **nodes** rather than objects — the folders are rows now and
    are deleted like anything else, so a run folder that reported three objects
    reports the five rows that describe them.

    Rows before blobs, for the reason `delete_objects` gives. The subtree bound
    is `catalog.subtree`'s and it refuses rather than truncates.
    """
    record, walked = _folder_at(lib, raw_prefix)

    result = catalog.delete_node(record["node_id"])
    s3.delete(result["blob_keys"])

    logger.info("Deleted folder %s (%d nodes)", record["node_id"], result["deleted"])
    return {"prefix": _as_prefix(walked), "deleted": result["deleted"]}
