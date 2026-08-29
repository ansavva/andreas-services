"""Moving, copying, deleting and editing nodes — the write half, addressed by id.

Everything destructive in studio lives here, in one module, on purpose: the read
paths in `browse` are allowed to be forgiving — a missing folder is an empty
listing — and nothing in here is. A write that cannot be described exactly is
refused.

**Every function here now takes node *records*, not name paths.** That is the
whole of what the entity model changed about this file. The name-path routes
(`/api/folder`, `/api/object`, `/api/objects/*`, `PATCH /api/text?key=`) are
gone, `_walk` went with them, and so did the `GetItem`-per-segment each of them
paid to turn a string into an id. One addressing scheme, no exceptions.

Records rather than ids because the caller has already read them: `routes/nodes`
resolves each id and checks it against the caller's memberships before anything
here runs, and passing the id back down would mean reading it twice and, worse,
would put a function here that could be called with an unchecked one.

## The rules that did not change

* **Nothing overwrites, and a condition expression is what says so.**
  `services.catalog` puts its `NAME#` item under `attribute_not_exists(pk)` and
  turns the cancelled transaction into the 409 the API returns.
* **Names are validated, never repaired.** `keys.clean_name` rejects a slash
  rather than escaping it, because "rename" and "move" are different requests
  and punctuation must not silently turn one into the other.
* **Scope is bounded before it is applied.** `catalog.subtree` refuses past
  `config.max_folder_objects` rather than starting work the Lambda's clock will
  interrupt — a refusal rather than a limit, because a truncated answer to a
  move or a delete is the setup for doing half the job and reporting success.

## What still touches S3, and in which order

Only bytes. `copy_nodes` issues one `CopyObject` per blob, the delete removes
blobs **after** their rows, and `update_text` overwrites one object.

The delete order is the recoverable one and is worth stating where it is
implemented: a row pointing at a blob that is gone is a broken tile in the grid,
while an orphan blob is invisible to every reader. If the second half fails, what
is left is the harmless kind of inconsistent.

**"Collectable later" used to be the end of that sentence, and the collector is
gone.** It was `studio catalog gc` — a CLI command holding its own boto3 clients,
listing every object in the bucket and scanning every row in the table to
reconstruct a list this module had already had in its hand and thrown away. All
of that existed because the delete told nobody which keys were in flight. It
tells them now: `catalog.open_sweep` writes them to a row *before* the rows that
name them are deleted, `release` closes that row once the bytes are gone, and
`drain` finishes any sweep an earlier request abandoned. The leftover is
addressed instead of searched for, and nothing has to scan anything.
"""

import logging

from studio_core import config
from studio_core.clients.aws import s3
from studio_core.errors import ConflictError, NotFoundError, ValidationError
from studio_core.services import browse, catalog, keys

logger = logging.getLogger(__name__)


def bulk(raw_ids: list | None, verb: str) -> list[str]:
    """Refuse a selection that is empty or larger than one request may carry.

    **The cap bounds a per-node cost rather than a single call**, and that is
    worth knowing before it is raised. `config.max_bulk_keys` is 1000 because
    `DeleteObjects` took 1000 keys per call, so a bulk delete was one round trip;
    against the catalog it is a transaction per node with the blobs still going
    in one call at the end. The bound is the same number guarding a different
    quantity, which is the kind of drift that only shows up as a timeout.

    Duplicates are collapsed here rather than at each call site. One node named
    twice in a selection used to be two `DeleteObject`s on one key, which S3
    treats as idempotent; a row deleted twice is a 404 raised *after* the first
    half of the request already applied.
    """
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ValidationError("ids must be a non-empty list")
    cap = config.max_bulk_keys()
    if len(raw_ids) > cap:
        raise ValidationError(f"cannot {verb} more than {cap} nodes in one request")
    for entry in raw_ids:
        if not isinstance(entry, str) or not entry:
            raise ValidationError("every id must be a string")
    return list(dict.fromkeys(raw_ids))


# ──────────────────────────────── move ────────────────────────────────


def move_nodes(records: list[dict], destination: dict) -> dict:
    """Move files and folders into another folder, keeping their names.

    **One route for both, where there used to be two.** `/api/objects/move` took
    files and `/api/folder/move` took a folder, and the split was an artefact of
    S3: moving a prefix meant a `CopyObject` per key underneath it and moving an
    object meant one. Neither copies anything now — a move rewrites one
    `parent_id`, one by-parent item and the derived `path` on every descendant —
    so the only thing the two verbs still differed in was the shape of their
    request.

    **Every destination is checked before any node moves.** Each `move_node` is
    its own transaction, so a conflict found on the eighth entry would leave
    seven already moved: a selection split across two folders with nothing to say
    where the boundary fell. The check is a read, and a read is beatable —
    another writer taking the name in between still surfaces as a 409 part-way
    through — but that is the rare case the check exists to make rare, and the
    transaction is what keeps the individual move from overwriting anything.

    Nodes already sitting in the destination are skipped and counted, because
    "move these forty there" is a reasonable thing to say when three of them are
    there already.
    """
    if destination["kind"] != catalog.KIND_FOLDER:
        raise ValidationError("the destination must be a folder")

    moving: list[dict] = []
    skipped = 0
    claimed: set[str] = set()

    for record in records:
        if record.get("parent_id") == destination["node_id"]:
            skipped += 1
            continue
        # Two sources with the same name would otherwise be one conflict against
        # the other, found half-way. A grid selection lives in one folder so its
        # names are already unique, but the endpoint does not require that and
        # must not depend on it.
        if record["name"] in claimed:
            raise ConflictError(f"two of these are named '{record['name']}'")
        claimed.add(record["name"])
        moving.append(record)

    for record in moving:
        if _taken(destination["node_id"], record["name"]):
            raise ConflictError(f"'{record['name']}' already exists there")

    descendants = 0
    for record in moving:
        descendants += catalog.move_node(record["node_id"], destination["node_id"])["descendants"]

    logger.info(
        "Moved %d nodes to %s (%d already there)", len(moving), destination["node_id"], skipped
    )
    return {
        "destination": destination["node_id"],
        "moved": len(moving),
        "skipped": skipped,
        "descendants": descendants,
        "ids": [record["node_id"] for record in moving],
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


# ──────────────────────────────── copy ────────────────────────────────


def copy_nodes(records: list[dict], destination: dict) -> dict:
    """Copy files into another folder, leaving the sources alone.

    **The only write in this service that copies bytes**, and that is the point
    of it rather than an oversight. Every other copy this module used to make was
    half of a rename or a move, and all of those are transactions now.

    **Files only.** A recursive folder copy is a different operation with a
    different cost — every descendant's bytes, not one selection's — and refusing
    it here is the same refusal `/api/objects/copy` always made, said out loud
    now that one route takes both kinds.

    **A name already taken at the destination is numbered, not refused.**
    `clip.mp4` arriving beside a `clip.mp4` becomes `clip (2).mp4`. A move refuses
    the whole request on a conflict because a half-done move splits a selection
    across two folders; a copy has no such split, and copying a file into a
    folder that already holds the name is the ordinary case rather than the edge.

    **Numbering consults names and nothing else.** An earlier version compared
    byte sizes so that re-copying an identical file was silently skipped — a copy
    quietly deciding not to copy. Ask for a copy, get a copy.

    **Each copy gets its own blob, and that is load-bearing rather than
    incidental.** A second row on one `blob_key` would be cheaper, but
    `catalog.delete_node` reports the keys it removed rows for without asking
    whether anything else still points at them — there is no index on `blob_key`
    — so a delete would destroy a surviving copy's bytes. Copy-on-write is #334
    and has to revisit that; until it does, "no two rows share a key" is held
    here, by the `CopyObject`.

    **The copy is stamped with the *destination's* owner**, which is the one
    place a blob key is chosen rather than inherited. Copying a run output into a
    character's reference pool files the new bytes under the character, because
    the new node is the character's — and the source object keeps its own key,
    untouched, because it is still the run's.
    """
    if destination["kind"] != catalog.KIND_FOLDER:
        raise ValidationError("the destination must be a folder")
    for record in records:
        if record["kind"] != catalog.KIND_FILE:
            raise ValidationError(f"'{record['name']}' is a folder — copy files, not folders")

    # Every source's bytes located before any row is written: one unreadable
    # source must not leave half a request applied.
    blobs = [(record, _source_blob(record)) for record in records]

    # Resolved once for the whole batch. Every copy lands in one folder, so every
    # one of them has the same owner, and asking per file would be a batched read
    # of the same ancestry forty times over.
    owner = catalog.blob_owner_for(destination["node_id"])

    # The destination's names, listed once and then kept current in memory, so a
    # bulk copy of forty costs one query rather than forty — and so two sources
    # sharing a name in one request number each other instead of both claiming
    # the same free one.
    taken = {entry["name"] for entry in catalog.children(destination["node_id"])}
    copied: list[dict] = []

    for record, (blob_key, metadata) in blobs:
        name = _free_copy_name(record["name"], taken)
        taken.add(name)

        # **The copy carries the caption.** A copy is a second print of the same
        # picture, so a description that was true of one is true of the other —
        # and a blank copy sitting beside a described original is drift nobody
        # would go looking for. The name is the only thing that may differ, and
        # only because the destination might already hold it.
        created = catalog.create_node(
            destination["node_id"], name, catalog.KIND_FILE, owner=owner,
            description=record.get("description"), tags=record.get("tags"),
        )
        s3.copy(blob_key, created["blob_key"])
        copied.append(
            catalog.set_blob(
                created["node_id"],
                created["blob_key"],
                size=metadata.get("ContentLength", 0),
                content_type=metadata.get("ContentType"),
            )
        )

    logger.info("Copied %d nodes into %s", len(copied), destination["node_id"])
    return {"destination": destination["node_id"], "copied": len(copied), "nodes": copied}


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

    for attempt in range(2, keys.MAX_NAME_VARIANTS + 1):
        candidate = keys.numbered_name(name, attempt)
        if candidate not in taken:
            return candidate

    raise ConflictError(
        f"'{name}' already names {keys.MAX_NAME_VARIANTS} files there — "
        "rename some of them first"
    )


# ──────────────────────────────── edit ────────────────────────────────


def update_text(record: dict, raw_content: str | None) -> dict:
    """Overwrite a text file's contents and restamp its row.

    The only write in this service that a person authors rather than the
    pipeline, and it is bounded on all four sides: the node must be a **file**
    that already has **bytes** (so this cannot create anything — studio's only
    upload is the presigned PUT in `routes/nodes`), of a **text kind** (so it
    cannot be pointed at a `.mp4`), whose new body is a **string** under
    `config.max_text_bytes`.

    **That last one is not a formality.** `browse.text_object` hands the editor a
    *truncated* copy of anything over the cap, and saving that back would delete
    the tail. The frontend refuses to open an editor on a truncated file, and the
    cap here means a file that somehow grew past it in between cannot be silently
    beheaded either.

    **The refusal that keeps "edit" from becoming "upload" is
    `browse.is_abandoned_upload`, and it has to be.** "Carries a `blob_key`"
    stopped meaning anything the day `create_node` began minting one for every
    file the moment the row exists — a placeholder whose bytes never landed has a
    key exactly like a file that has them. The distinction is `"size" in record`:
    a confirmed empty file has `size` 0 and a placeholder has it absent. It is
    asked through the one function that owns that reading rather than inlined
    here, which is what stops the two copies drifting.

    Without it this route would quietly *create* the object, and studio would
    have a second upload path nobody designed — one with no signed length, no
    signed content type and no 6 MB ceiling.

    **Bytes first, then the row** — the reverse of a delete, for the same reason
    the delete is the way round it is. `size` on the row is a claim about an
    object; writing it before the object exists would be a claim about bytes that
    were never stored, and a listing reports that number without re-reading S3.
    """
    if record["kind"] != catalog.KIND_FILE:
        raise ValidationError("a folder has no contents to edit")

    name = record["name"]
    if keys.kind(name) != "text":
        raise ValidationError("this is not an editable text file")
    if not isinstance(raw_content, str):
        raise ValidationError("content must be a string")

    body = raw_content.encode("utf-8")
    cap = config.max_text_bytes()
    if len(body) > cap:
        raise ValidationError(f"content must be smaller than {cap} bytes")

    blob_key = record.get("blob_key")
    if not blob_key or browse.is_abandoned_upload(record):
        raise NotFoundError(name)

    content_type = keys.content_type(name)
    s3.put_text(blob_key, body, content_type)
    catalog.set_blob(record["node_id"], blob_key, size=len(body), content_type=content_type)

    logger.info("Saved %d bytes to %s", len(body), record["node_id"])
    return {
        "id": record["node_id"],
        "name": name,
        "language": keys.language(name),
        "bytes": len(body),
    }


# ─────────────────────────────── delete ───────────────────────────────


def delete_nodes(records: list[dict]) -> dict:
    """Delete files and folders, rows first and then blobs.

    Bulk and single are the same call because the grid's selection is the reason
    delete exists at all — a viewer that could only remove one file at a time
    would not be worth the write permission this endpoint needs. Folders come in
    through the same door for the reason `move_nodes` gives: the difference
    between the two used to be a `CopyObject` per key and is now nothing.

    **Every row goes before any blob does**, and the blobs go in one call at the
    end rather than one per file. The order is the recoverable one: a row
    pointing at a blob that is gone is a broken tile the user sees, while the
    reverse leaves an object no reader can reach.

    **That leftover used to be found by scanning, and is now addressed.**
    `catalog.delete_node` opens a sweep naming the keys before the rows go, so
    `release` below has a list to work from and the next delete finishes any
    sweep this one abandons. `studio catalog gc` listed the whole bucket against
    the whole table to reconstruct the same list; it is deleted.

    **An entity's root folder is refused**, naming the entity to delete instead —
    and refused for *every* record before any of them is touched. That pre-pass
    is `catalog.assert_deletable` and it exists because the refusal inside
    `delete_node` comes too late for a selection: the eighth entry refusing would
    leave seven already gone.
    """
    for record in records:
        catalog.assert_deletable(record)

    blob_keys: list[str] = []
    sweeps: list[str] = []
    for record in records:
        freed = catalog.delete_node(record["node_id"])
        blob_keys.extend(freed["blob_keys"])
        sweeps.extend(freed["sweep"])

    lib = records[0]["lib"] if records else None
    release(lib, blob_keys, sweeps)

    logger.info("Deleted %d nodes and %d blobs", len(records), len(blob_keys))
    return {"deleted": len(records), "ids": [record["node_id"] for record in records]}


def release(lib: str | None, blob_keys: list[str], sweeps: list[str]) -> None:
    """Delete the bytes a row-delete freed, then close the sweeps that named them.

    **The one place blobs are deleted, and the reason no route handles a
    `blob_key` any more.** Seven call sites each did `if result["blob_keys"]:
    s3.delete(...)`, which is the line an interruption lands between — and the
    line whose leftovers `studio catalog gc` existed to find. Doing it here means
    the sweep is closed by whatever deleted the bytes, so the two can never
    disagree about whether the job finished.

    Ordered bytes-then-sweep on purpose. A sweep outliving its objects costs one
    wasted recheck on the next delete; a sweep closed before its objects go is an
    orphan nothing will ever look for again.
    """
    if blob_keys:
        s3.delete(blob_keys)
    catalog.close_sweep(lib, sweeps)


def drain(lib: str) -> int:
    """Finish any sweep an earlier delete left open. Answers how many blobs went.

    **Called at the top of every delete route**, which is the only moment a
    sweep can exist and the only moment anybody is owed one being gone. That is
    the whole of the replacement for a scheduled collector: the thing that
    creates the debt is the thing that pays it, one request later.

    **A key whose node is still live is kept and its sweep left open.** That is
    the crash-between-open-and-delete case: the sweep was written, the rows were
    not deleted, and the bytes are still referenced. Deleting them would be the
    exact failure the row-first order exists to prevent, so the recheck decides
    and the sweep waits for the delete to be retried.

    A sweep may be part-live, and then the dead half still goes: those bytes are
    genuinely unreachable and holding them hostage to their siblings buys
    nothing. The sweep stays open and names them again next time, which costs a
    second `DeleteObjects` on keys that are already gone — a no-op in S3, and
    cheaper than rewriting the row to remove them.

    Failures are swallowed and logged. A delete must not 500 because a *previous*
    delete's cleanup could not finish — the sweep survives either way and the
    next request tries again, which is the property that makes this safe to do
    opportunistically at all.
    """
    try:
        pending = catalog.pending_sweeps(lib)
    except Exception:
        logger.exception("Could not read pending sweeps for %s", lib)
        return 0
    if not pending:
        return 0

    collected = 0
    for row in pending:
        try:
            blobs = row.get("blobs") or []
            live = catalog.live_nodes([entry["node"] for entry in blobs])
            doomed = [entry["key"] for entry in blobs if entry["node"] not in live]
            if doomed:
                s3.delete(doomed)
                collected += len(doomed)
            if len(doomed) < len(blobs):
                logger.info("Sweep %s: %d of %d keys still referenced — left open",
                            row.get("sweep"), len(blobs) - len(doomed), len(blobs))
                continue
            catalog.close_sweep(lib, [row["sk"]])
        except Exception:
            logger.exception("Could not drain sweep %s", row.get("sweep"))

    if collected:
        logger.info("Drained %d abandoned blob(s) in %s", collected, lib)
    return collected
