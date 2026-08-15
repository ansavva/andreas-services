"""Browsing the media bucket: folder listings, the recursive reel walk, and text.

The bucket's directory structure is the product here, so nothing in this module
flattens or reinterprets it. Run metadata (`request.json`, `result.json`,
`prompt.json`) is deliberately *not* parsed — those files are served as text and
the frontend shows them read-only, which keeps this service honest when the
x-harness pipeline changes their shape.
"""

import logging

from studio_core import config
from studio_core.clients.aws import s3
from studio_core.errors import ValidationError
from studio_core.services import keys

logger = logging.getLogger(__name__)

REEL_KINDS = frozenset({"image", "video"})
DEFAULT_REEL_PAGE_SIZE = 200
MAX_REEL_PAGE_SIZE = 1000

# How many undelimited pages one `/api/reel` request will walk before returning
# what it has. A run folder is mostly JSON, so a page of 1000 keys can yield very
# few playable items; without this the caller sees an empty page and a token and
# has to spin. With it, a request does a bounded amount of work and still makes
# progress.
MAX_REEL_PAGES_PER_REQUEST = 10


def _file_entry(obj: dict, *, presigned: bool = True) -> dict:
    key = obj["Key"]
    last_modified = obj.get("LastModified")
    entry = {
        "key": key,
        "name": keys.basename(key),
        "size": obj.get("Size", 0),
        "last_modified": last_modified.isoformat() if last_modified else None,
        "kind": keys.kind(key),
    }
    if presigned:
        entry["url"] = s3.presign(key)
    if entry["kind"] == "text":
        entry["language"] = keys.language(key)
    return entry


def list_folder(raw_prefix: str | None) -> dict:
    """Immediate contents of one folder, ready to render."""
    prefix = keys.clean_prefix(raw_prefix)
    folder_prefixes, objects = s3.list_folder(prefix)

    files = [
        _file_entry(obj)
        for obj in objects
        # The prefix itself comes back as a zero-byte object in a delimited
        # listing; so do console-created folder markers. Neither is a file.
        if obj["Key"] != prefix and not keys.is_folder_marker(obj["Key"], obj.get("Size", 0))
    ]
    files.sort(key=lambda entry: entry["name"].lower())

    folders = [
        {"prefix": folder, "name": keys.basename(folder)}
        for folder in sorted(folder_prefixes)
    ]

    return {
        "prefix": prefix,
        "breadcrumbs": keys.breadcrumbs(prefix),
        "folders": folders,
        "files": files,
        "counts": {
            "folders": len(folders),
            "files": len(files),
            "media": sum(1 for f in files if f["kind"] in REEL_KINDS),
        },
    }


def reel_items(raw_prefix: str | None, cursor: str | None, page_size: int | None) -> dict:
    """Every image and video beneath a prefix, recursively, one page at a time.

    Ordered by key, which is what makes the reel stable and predictable: a
    subject's `input/`, `originals/`, `reference/` and then `runs/` in timestamp
    order, because the run folders are named with a sortable timestamp.
    """
    prefix = keys.clean_prefix(raw_prefix)
    limit = _reel_page_size(page_size)

    items: list[dict] = []
    token = cursor or None
    pages = 0

    while pages < MAX_REEL_PAGES_PER_REQUEST:
        objects, token = s3.walk(prefix, token, limit)
        pages += 1

        for obj in objects:
            if keys.is_folder_marker(obj["Key"], obj.get("Size", 0)):
                continue
            if keys.kind(obj["Key"]) not in REEL_KINDS:
                continue
            items.append(_file_entry(obj))

        if token is None or len(items) >= limit:
            break

    return {"prefix": prefix, "items": items, "next_cursor": token}


def _reel_page_size(raw: int | str | None) -> int:
    if raw in (None, ""):
        return DEFAULT_REEL_PAGE_SIZE
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError("page_size must be an integer") from None
    if value < 1:
        raise ValidationError("page_size must be positive")
    return min(value, MAX_REEL_PAGE_SIZE)


def asset_url(raw_key: str, disposition: str | None) -> dict:
    """A fresh presigned URL for one object.

    Used both to drive downloads and to re-sign a URL the browser found expired,
    which is why it exists separately from the listing endpoints.
    """
    key = keys.clean_key(raw_key)
    if disposition not in (None, "", "inline", "attachment"):
        raise ValidationError("disposition must be 'inline' or 'attachment'")

    # HEAD before signing so a mistyped key is a clean 404 rather than a URL that
    # only fails once the browser follows it.
    metadata = s3.head(key)

    return {
        "key": key,
        "name": keys.basename(key),
        "kind": keys.kind(key),
        "size": metadata.get("ContentLength", 0),
        "content_type": metadata.get("ContentType"),
        "expires_in": config.presign_ttl_seconds(),
        "url": s3.presign(key, disposition=disposition or "inline"),
    }


def text_object(raw_key: str) -> dict:
    """An object's contents as text, for the read-only viewer.

    Serving this through the API rather than letting the viewer fetch the
    presigned URL keeps it on one authenticated same-origin request — a
    cross-origin `fetch` to S3 would need CORS on a bucket this service does not
    own and must not modify.
    """
    key = keys.clean_key(raw_key)
    if keys.kind(key) != "text":
        raise ValidationError("key is not a viewable text file")

    cap = config.max_text_bytes()
    # One byte over the cap tells us it was truncated without reading it all.
    body = s3.get_body(key, cap + 1)
    truncated = len(body) > cap
    if truncated:
        body = body[:cap]

    return {
        "key": key,
        "name": keys.basename(key),
        "language": keys.language(key),
        "truncated": truncated,
        "content": body.decode("utf-8", errors="replace"),
    }
