"""Creating, renaming and deleting things in the media bucket.

Everything destructive in studio lives here, in one module, on purpose: the read
paths in `browse` are allowed to be forgiving — a missing folder is an empty
listing — and nothing in here is. A write that cannot be described exactly is
refused.

Three rules hold across every function:

* **Names are validated, never repaired.** `keys.clean_name` rejects a slash
  rather than escaping it, because "rename" and "move" are different requests
  and punctuation must not silently turn one into the other.
* **Nothing overwrites.** S3 has no conditional put, so every rename and create
  checks its destination first and raises `ConflictError` instead. The check is
  not a transaction and cannot be — two callers racing on the same name is a
  real if unlikely outcome — but a UI-driven library has one user, and the
  alternative is a rename that eats a file.
* **Scope is bounded before it is applied.** A folder operation counts the
  subtree and refuses past `config.max_folder_objects` rather than starting work
  the Lambda's clock will interrupt. A rename that timed out halfway would leave
  the same objects under two prefixes with no record of which half moved.

Renames are copy-then-delete, in that order, and never the reverse. If the
delete fails the library holds a duplicate, which is visible and fixable; if the
order were reversed the failure would be data loss.
"""

import logging

from studio_core import config
from studio_core.clients.aws import s3
from studio_core.errors import ConflictError, NotFoundError, ValidationError
from studio_core.services import keys

logger = logging.getLogger(__name__)


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
