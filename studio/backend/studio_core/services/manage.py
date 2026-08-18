"""Creating, renaming, moving, deleting and editing things in the media bucket.

Everything destructive in studio lives here, in one module, on purpose: the read
paths in `browse` are allowed to be forgiving — a missing folder is an empty
listing — and nothing in here is. A write that cannot be described exactly is
refused.

Three rules hold across every function:

* **Names are validated, never repaired.** `keys.clean_name` rejects a slash
  rather than escaping it, because "rename" and "move" are different requests
  and punctuation must not silently turn one into the other. Move is a separate
  pair of functions below, and it takes a *destination prefix* rather than a
  name — so the two requests stay distinguishable all the way down to S3 and
  neither can be reached by typing the other one carelessly.
* **Nothing overwrites.** S3 has no conditional put, so every rename and create
  checks its destination first and raises `ConflictError` instead. The check is
  not a transaction and cannot be — two callers racing on the same name is a
  real if unlikely outcome — but a UI-driven library has one user, and the
  alternative is a rename that eats a file.
* **Scope is bounded before it is applied.** A folder operation counts the
  subtree and refuses past `config.max_folder_objects` rather than starting work
  the Lambda's clock will interrupt. A rename that timed out halfway would leave
  the same objects under two prefixes with no record of which half moved.

Renames and moves are copy-then-delete, in that order, and never the reverse. If
the delete fails the library holds a duplicate, which is visible and fixable; if
the order were reversed the failure would be data loss.

`copy_objects` is the exception that proves the ordering rule: it is a copy with
**no** delete, because the source stays where it was. It takes the same
`{keys, destination}` a move does, and differs in exactly two places — nothing is
deleted, and a name already taken at the destination is numbered rather than
refused.

`update_text` is the odd one out and is deliberately kept here rather than in
`browse` beside the endpoint that reads the same files: it writes, and this
module is the answer to "what can this service change".
"""

import logging

from studio_core import config
from studio_core.clients.aws import s3
from studio_core.errors import ConflictError, NotFoundError, ValidationError
from studio_core.services import browse, keys

logger = logging.getLogger(__name__)

# How many `name (n).ext` variants one name may spawn in a destination before the
# request is refused. Generous — copying the same clip into one folder twice is
# ordinary — but finite, so a script cannot fill a folder with numbered copies.
MAX_COPY_VARIANTS = 100


def create_folder(raw_prefix: str | None, raw_name: str | None) -> dict:
    """Create an empty folder inside `raw_prefix`.

    S3 has no directories, so this writes the same zero-byte marker object the
    console does. `browse` filters those back out of every listing, which is why
    a folder made here shows up as a folder and never as a 0 B file.
    """
    parent = keys.clean_prefix(raw_prefix)
    name = keys.clean_name(raw_name)
    prefix = f"{parent}{name}/"

    if s3.prefix_exists(prefix):
        raise ConflictError(f"'{name}' already exists here")

    s3.put_folder_marker(prefix)
    logger.info("Created folder %s", prefix)
    return {"prefix": prefix, "name": name}


def rename_object(raw_key: str | None, raw_name: str | None) -> dict:
    """Rename one object within its own folder."""
    key = keys.clean_key(raw_key)
    name = keys.clean_name(raw_name)
    destination = keys.with_name(key, name)

    if destination == key:
        return {"key": key, "name": name, "renamed": False}
    if s3.exists(destination):
        raise ConflictError(f"'{name}' already exists here")
    if not s3.exists(key):
        raise NotFoundError(key)

    s3.copy(key, destination)
    s3.delete([key])
    logger.info("Renamed object %s -> %s", key, destination)
    return {"key": destination, "name": name, "renamed": True}


def rename_folder(raw_prefix: str | None, raw_name: str | None) -> dict:
    """Rename a folder, and everything beneath it, within its own parent.

    A prefix rename is not an operation S3 offers — it is a copy and a delete per
    key, which is why this counts first and refuses a subtree bigger than the
    Lambda can finish.
    """
    prefix = keys.clean_prefix(raw_prefix)
    keys.assert_inside_root(prefix)
    name = keys.clean_name(raw_name)
    destination = keys.renamed_prefix(prefix, name)

    if destination == prefix:
        return {"prefix": prefix, "name": name, "objects": 0, "renamed": False}
    if s3.prefix_exists(destination):
        raise ConflictError(f"'{name}' already exists here")

    objects = _subtree(prefix)
    moved = [obj["Key"] for obj in objects]

    for source in moved:
        s3.copy(source, f"{destination}{source[len(prefix):]}")
    s3.delete(moved)

    logger.info("Renamed folder %s -> %s (%d objects)", prefix, destination, len(moved))
    return {"prefix": destination, "name": name, "objects": len(moved), "renamed": True}


def move_objects(raw_keys: list | None, raw_destination: str | None) -> dict:
    """Move one or many objects into another folder, keeping their names.

    The counterpart of `rename_object`: that one changes the last segment and
    keeps the folder, this one changes the folder and keeps the last segment.
    Neither can do the other's job, which is the point — a caller cannot reach a
    move by putting a slash in a name, and cannot reach a rename by naming a
    destination.

    **Every destination is checked before any object is copied.** A bulk move
    that stopped halfway would leave a selection split across two folders with
    nothing to say where the boundary fell, so a single conflict refuses the
    whole request. Objects already sitting in the destination are not a conflict
    — they are skipped and counted, because "move these forty files there" is a
    reasonable thing to say when three of them are there already.
    """
    if not isinstance(raw_keys, list) or not raw_keys:
        raise ValidationError("keys must be a non-empty list")

    cap = config.max_bulk_keys()
    if len(raw_keys) > cap:
        raise ValidationError(f"cannot move more than {cap} objects in one request")

    destination = keys.clean_prefix(raw_destination)
    cleaned = [keys.clean_key(raw) for raw in raw_keys]

    moves: list[tuple[str, str]] = []
    skipped = 0
    claimed: set[str] = set()

    for source in cleaned:
        target = f"{destination}{keys.basename(source)}"
        if target == source:
            skipped += 1
            continue
        # Two sources with the same basename would otherwise silently overwrite
        # one another at the destination. A grid selection lives in one folder
        # so its names are already unique, but the endpoint does not require
        # that and must not depend on it.
        if target in claimed:
            raise ConflictError(f"two of these files are named '{keys.basename(source)}'")
        if s3.exists(target):
            raise ConflictError(f"'{keys.basename(source)}' already exists there")
        claimed.add(target)
        moves.append((source, target))

    for source, target in moves:
        s3.copy(source, target)
    s3.delete([source for source, _ in moves])

    logger.info("Moved %d objects to %s (%d already there)", len(moves), destination, skipped)
    return {
        "destination": destination,
        "moved": len(moves),
        "skipped": skipped,
        "keys": [target for _, target in moves],
    }


def move_folder(raw_prefix: str | None, raw_destination: str | None) -> dict:
    """Move a folder, and everything beneath it, under a different parent.

    Two refusals carry the weight here. A folder cannot be moved into itself or
    into anything beneath itself — `characters/<name>/` into
    `characters/<name>/seed/` — which would otherwise be a copy loop whose source
    grows as fast as it is read. And the destination cannot already hold a
    folder of this name, because merging two trees is not a thing this can do
    safely: the per-key conflicts would be found halfway through the copy.
    """
    prefix = keys.clean_prefix(raw_prefix)
    keys.assert_inside_root(prefix)
    parent = keys.clean_prefix(raw_destination)
    name = keys.basename(prefix)
    destination = keys.moved_prefix(prefix, parent)

    if destination == prefix:
        return {"prefix": prefix, "name": name, "objects": 0, "moved": False}
    if keys.is_within(prefix, parent):
        raise ValidationError("a folder cannot be moved inside itself")
    if s3.prefix_exists(destination):
        raise ConflictError(f"'{name}' already exists there")

    objects = _subtree(prefix)
    if not objects:
        raise NotFoundError(prefix)

    moved = [obj["Key"] for obj in objects]
    for source in moved:
        s3.copy(source, f"{destination}{source[len(prefix):]}")
    s3.delete(moved)

    logger.info("Moved folder %s -> %s (%d objects)", prefix, destination, len(moved))
    return {"prefix": destination, "name": name, "objects": len(moved), "moved": True}


def copy_objects(raw_keys: list | None, raw_destination: str | None) -> dict:
    """Copy one or many objects into another folder, keeping their names.

    **The only write in this service that copies without deleting**, and that is
    the point of it rather than an oversight. Every other copy here is half of a
    rename or a move. It is still not an upload — the bytes come from an object
    already in the bucket, server-side, and nothing about this endpoint can bring
    in a file from outside.

    It takes the same `{keys, destination}` as `move_objects` and differs in two
    places:

    * **Nothing is deleted.** The sources stay where they are.
    * **A name already taken at the destination is numbered, not refused.**
      `clip.mp4` arriving beside a `clip.mp4` becomes `clip (2).mp4`. A move
      refuses the whole request on a conflict because a half-done move leaves a
      selection split across two folders with nothing to say where the boundary
      fell; a copy has no such split, and copying a file into a folder that
      already holds the name is the ordinary case rather than the edge.

    **Numbering does not consult what is already there beyond the names.** An
    earlier version of this compared byte sizes so that re-copying an identical
    file was silently skipped — which is a copy quietly deciding not to copy, and
    is the same "has this been done already" bookkeeping the favourites feature
    was removed for. Ask for a copy, get a copy.

    Nothing is overwritten in any branch, which is the rule the rest of this
    module holds to as well.
    """
    if not isinstance(raw_keys, list) or not raw_keys:
        raise ValidationError("keys must be a non-empty list")

    cap = config.max_bulk_keys()
    if len(raw_keys) > cap:
        raise ValidationError(f"cannot copy more than {cap} objects in one request")

    destination = keys.clean_prefix(raw_destination)
    cleaned = [keys.clean_key(raw) for raw in raw_keys]

    # Listed once and then kept current in memory, so a bulk copy of forty costs
    # one listing rather than forty — and so two sources sharing a basename in
    # one request number each other correctly instead of both claiming the same
    # free name.
    taken = browse.folder_names(destination)
    copies: list[tuple[str, str]] = []

    for source in cleaned:
        name = _free_copy_name(keys.basename(source), taken)
        taken.add(name)
        copies.append((source, f"{destination}{name}"))

    for source, target in copies:
        s3.copy(source, target)

    logger.info("Copied %d objects to %s", len(copies), destination)
    return {
        "destination": destination,
        "copied": len(copies),
        "keys": [target for _, target in copies],
    }


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


def update_text(raw_key: str | None, raw_content: str | None) -> dict:
    """Overwrite a text file's contents.

    The only write in this service that a person authors rather than the
    pipeline, and it is bounded on all four sides: the key must name an object
    that already **exists** (so this cannot create a file — studio still has no
    upload), of a **text kind** (so it cannot be pointed at a `.mp4`), whose new
    body is a **string** under `config.max_text_bytes` (the same cap the read
    endpoint truncates at, which is what makes the pairing honest).

    That last one is not a formality. `browse.text_object` hands the editor a
    *truncated* copy of anything over the cap, and saving that back would delete
    the tail. The frontend refuses to open an editor on a truncated file, and
    the cap here means a file that somehow grew past it in between cannot be
    silently beheaded either.
    """
    key = keys.clean_key(raw_key)
    if keys.kind(key) != "text":
        raise ValidationError("key is not an editable text file")
    if not isinstance(raw_content, str):
        raise ValidationError("content must be a string")

    body = raw_content.encode("utf-8")
    cap = config.max_text_bytes()
    if len(body) > cap:
        raise ValidationError(f"content must be smaller than {cap} bytes")

    if not s3.exists(key):
        raise NotFoundError(key)

    s3.put_text(key, body, keys.content_type(key))
    logger.info("Saved %d bytes to %s", len(body), key)
    return {
        "key": key,
        "name": keys.basename(key),
        "language": keys.language(key),
        "bytes": len(body),
    }


def delete_objects(raw_keys: list | None) -> dict:
    """Delete one or many objects.

    Bulk and single are the same call because the grid's selection is the reason
    delete exists at all — a viewer that could only remove one file at a time
    would not be worth the write permission this endpoint needs.
    """
    if not isinstance(raw_keys, list) or not raw_keys:
        raise ValidationError("keys must be a non-empty list")

    cap = config.max_bulk_keys()
    if len(raw_keys) > cap:
        raise ValidationError(f"cannot delete more than {cap} objects in one request")

    # Every key is validated before any key is deleted: a request that names one
    # bad key does nothing at all rather than deleting the good ones first and
    # then failing.
    cleaned = [keys.clean_key(raw) for raw in raw_keys]

    s3.delete(cleaned)
    logger.info("Deleted %d objects", len(cleaned))
    return {"deleted": len(cleaned), "keys": cleaned}


def delete_folder(raw_prefix: str | None) -> dict:
    """Delete a folder and everything beneath it."""
    prefix = keys.clean_prefix(raw_prefix)
    keys.assert_inside_root(prefix)

    objects = _subtree(prefix)
    if not objects:
        raise NotFoundError(prefix)

    s3.delete([obj["Key"] for obj in objects])
    logger.info("Deleted folder %s (%d objects)", prefix, len(objects))
    return {"prefix": prefix, "deleted": len(objects)}


def _subtree(prefix: str) -> list[dict]:
    """Every object under a prefix, refusing rather than truncating.

    `walk_all` stops at the cap and says so; for a read that is a page boundary,
    but for a rename or a delete a truncated answer is the setup for doing half
    the job. So the cap is a refusal here, not a limit.
    """
    cap = config.max_folder_objects()
    objects, truncated = s3.walk_all(prefix, cap + 1)
    if truncated or len(objects) > cap:
        raise ValidationError(
            f"this folder holds more than {cap} objects — "
            "delete or rename it from the pipeline instead"
        )
    return objects
