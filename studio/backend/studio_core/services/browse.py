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

# The four orders every listing endpoint accepts. `newest` is the default
# because this is a library of generated output: what you came to look at is
# almost always what the pipeline produced most recently, and the old behaviour
# — name ascending — buried it under whatever happened to sort first.
SORTS = frozenset({"newest", "oldest", "name", "name_desc"})
DEFAULT_SORT = "newest"

# The epoch, for objects a listing gave no LastModified for. Sorting newest-first
# puts them last, which is where an object we know nothing about belongs.
_UNDATED = ""


def clean_sort(raw: str | None) -> str:
    if raw in (None, ""):
        return DEFAULT_SORT
    if raw not in SORTS:
        raise ValidationError(f"sort must be one of {', '.join(sorted(SORTS))}")
    return raw


def _file_entry(obj: dict, *, presigned: bool = True) -> dict:
    key = obj["Key"]
    last_modified = obj.get("LastModified")
    entry = {
        "key": key,
        "name": keys.basename(key),
        "size": obj.get("Size", 0),
        "last_modified": last_modified.isoformat() if last_modified else None,
        "kind": keys.kind(key),
        # Where a favourite of this would go, and whether it is one already. The
        # first is pure string work; the second is only *half* answered here —
        # a key inside a favourites folder is self-evidently a favourite, and
        # anything else needs the listing `_mark_favorited` does.
        "favorites_prefix": keys.favorites_prefix(key),
        "favorited": keys.is_favorite(key),
    }
    if presigned:
        entry["url"] = s3.presign(key)
    if entry["kind"] == "text":
        entry["language"] = keys.language(key)
    return entry


def favorites_index(prefix: str) -> dict[str, int]:
    """What one favourites folder already holds, as `{name: size}`.

    Name *and* size, because that pair is what stands in for "is this the same
    file". Studio has nothing that records where a favourite was copied from —
    it is a flat shelf of objects, deliberately, and adding provenance metadata
    would be studio inventing a format inside a bucket x-harness owns. So a
    favourite matches its source when the name and the byte count both match,
    which is wrong only for two genuinely different clips that share a name and
    are the same length to the byte.

    Used by `manage.favorite_objects` to decide between skipping and numbering,
    and by `_mark_favorited` to fill in a star.
    """
    _, objects = s3.list_folder(prefix)
    return {
        keys.basename(obj["Key"]): obj.get("Size", 0)
        for obj in objects
        if obj["Key"] != prefix and not keys.is_folder_marker(obj["Key"], obj.get("Size", 0))
    }


def _mark_favorited(entries: list[dict]) -> None:
    """Fill in `favorited` for entries whose favourite would live elsewhere.

    One extra listing per *distinct* favourites folder, which for a folder view
    is one call and for a reel page is one per project on the page — a handful
    at the very worst, since a page is 200 items and the bucket holds three
    subjects. Cheap enough to be worth a star that survives a reload: without
    this the button could only report what you pressed this session, and would
    go hollow again on refresh over a file that is very much still favourited.

    Deliberately called on the *presigned window* in the reel rather than on the
    whole sorted walk — the walk can be twenty thousand entries and only two
    hundred of them are about to be rendered.
    """
    wanted = {entry["favorites_prefix"] for entry in entries if entry["favorites_prefix"]}
    if not wanted:
        return

    index = {prefix: favorites_index(prefix) for prefix in sorted(wanted)}
    for entry in entries:
        prefix = entry["favorites_prefix"]
        if prefix:
            entry["favorited"] = index[prefix].get(entry["name"]) == entry["size"]


def _sort_files(files: list[dict], sort: str) -> None:
    """Order file entries in place.

    Ties break on the full key, always *ascending* — including under `newest`,
    which is why this is two passes rather than one `reverse=True` over a
    composite key. S3's LastModified has one-second resolution and a run writes
    its whole output inside one second, so ties are the common case here, not
    the edge: the composite-key form would hand back `frame_9, frame_8, frame_7`
    for every such run. Python's sort is stable and `reverse=True` does not
    reverse equal elements, so sorting by key first and then by date preserves
    it.

    The tie-break is the key rather than the name because the reel walks
    recursively. Breaking on the basename would interleave `originals/`,
    `reference/` and `runs/` output whenever their timestamps matched, which is
    to say almost always; breaking on the key keeps a subject's folders whole
    and reproduces the ordering the reel had before it could be sorted at all.
    In a single folder's listing the two are the same thing.
    """
    files.sort(key=lambda entry: entry["key"])
    if sort in ("newest", "oldest"):
        files.sort(
            key=lambda entry: entry["last_modified"] or _UNDATED,
            reverse=sort == "newest",
        )
    elif sort == "name":
        files.sort(key=lambda entry: entry["name"].lower())
    elif sort == "name_desc":
        files.sort(key=lambda entry: entry["name"].lower(), reverse=True)


def _sort_folders(folders: list[dict], sort: str) -> None:
    """Order folder entries in place — by name, and by name for dates too.

    A delimited listing returns common prefixes and nothing else: a folder has no
    LastModified, because a folder is not an object. Rather than HEAD every one
    of them to invent a date, the date orders fall back to the name, which is
    the right answer for the folders that matter — x-harness names every run
    `<date>_<time>_<slug>`, so descending by name *is* newest-first. For a folder
    named something else it is alphabetical, which is no worse than the arbitrary
    order the alternative would produce.
    """
    folders.sort(key=lambda entry: entry["name"].lower(), reverse=sort in ("newest", "name_desc"))


def list_folder(raw_prefix: str | None, raw_sort: str | None = None) -> dict:
    """Immediate contents of one folder, ready to render."""
    prefix = keys.clean_prefix(raw_prefix)
    sort = clean_sort(raw_sort)
    folder_prefixes, objects = s3.list_folder(prefix)

    files = [
        _file_entry(obj)
        for obj in objects
        # The prefix itself comes back as a zero-byte object in a delimited
        # listing; so do console-created folder markers. Neither is a file.
        if obj["Key"] != prefix and not keys.is_folder_marker(obj["Key"], obj.get("Size", 0))
    ]
    _sort_files(files, sort)
    _mark_favorited(files)

    folders = [
        {"prefix": folder, "name": keys.basename(folder)} for folder in folder_prefixes
    ]
    _sort_folders(folders, sort)

    return {
        "prefix": prefix,
        "sort": sort,
        "breadcrumbs": keys.breadcrumbs(prefix),
        "folders": folders,
        "files": files,
        "counts": {
            "folders": len(folders),
            "files": len(files),
            "media": sum(1 for f in files if f["kind"] in REEL_KINDS),
        },
    }


def reel_items(
    raw_prefix: str | None,
    cursor: str | None,
    page_size: int | None,
    raw_sort: str | None = None,
) -> dict:
    """Every image and video beneath a prefix, recursively, one page at a time.

    **The whole subtree is listed on every request, and the cursor is an offset
    into the sorted result rather than S3's continuation token.** That is a
    change forced by sorting: a continuation token walks keys in lexicographic
    order and nothing else, so paging that way can only ever produce key order.
    To hand back the newest item first you have to know what the newest item is,
    and that means seeing all of them.

    It costs less than it sounds. `ListObjectsV2` returns LastModified and Size
    inline, so ordering by date needs no extra call, and the listing is capped by
    `config.max_walk_objects`. Presigning happens *after* the slice, so a request
    signs one page's worth of URLs instead of the whole library's — which is
    strictly cheaper than the previous behaviour.
    """
    prefix = keys.clean_prefix(raw_prefix)
    limit = _reel_page_size(page_size)
    sort = clean_sort(raw_sort)
    offset = _reel_offset(cursor)

    objects, truncated = s3.walk_all(prefix, config.max_walk_objects())

    entries = [
        _file_entry(obj, presigned=False)
        for obj in objects
        if not keys.is_folder_marker(obj["Key"], obj.get("Size", 0))
        and keys.kind(obj["Key"]) in REEL_KINDS
    ]
    _sort_files(entries, sort)

    window = entries[offset : offset + limit]
    for entry in window:
        entry["url"] = s3.presign(entry["key"])
    _mark_favorited(window)

    next_offset = offset + len(window)
    return {
        "prefix": prefix,
        "sort": sort,
        "items": window,
        "total": len(entries),
        # True when the *bucket walk* was cut short, not the page — the caller
        # is showing a library that has more in it than this endpoint will admit
        # to, and should say so rather than imply the tail does not exist.
        "truncated": truncated,
        "next_cursor": str(next_offset) if next_offset < len(entries) else None,
    }


def _reel_offset(cursor: str | None) -> int:
    if cursor in (None, ""):
        return 0
    try:
        value = int(cursor)
    except (TypeError, ValueError):
        raise ValidationError("cursor is not valid") from None
    if value < 0:
        raise ValidationError("cursor is not valid")
    return value


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
