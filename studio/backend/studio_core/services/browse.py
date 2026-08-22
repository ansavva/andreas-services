"""Browsing the library: folder listings, the recursive reel, and text.

**Listings no longer list S3.** Folders, files, names, sizes and timestamps are
rows in the catalog (#309–#311); `presign` is the only S3 call left in the
listing path, and it is handed a `blob_key` that never leaves this module. What
that retires is stated where each workaround used to live — `_sort_records` for
the date-tie break, `_folder_entry` for "a folder has no LastModified",
`reel_items` for the twenty-thousand-object walk.

`asset_url` and `text_object` below **address the catalog too now** (#432). Both
take `?node=<id>`, both refuse it alongside a `key`, and `GET /api/text` walks a
name path exactly as `PATCH /api/text` does — the pair had drifted into
addressing two different things, which is what #432 was filed about. What they
could not reach before was anything written since the catalog: a row minted by
#294 keeps its bytes at `blobs/<node-id>`, and no client is ever handed that
string.

**One raw S3 key survives, on `/api/asset?key=`, and it is not an oversight.**
Shared material — `phrasebook/wording.yaml`, the `config/pose/` plates — belongs
to no character and no project and deliberately has no node, so there is no id
and no name path that can address it. `keys.clean_key` and the traversal rules
under it stay alive for that one parameter; #312 expected to take them and
cannot.

Run metadata (`request.json`, `result.json`, `prompt.json`) is deliberately
*not* parsed — those files are served as text and the frontend shows them
read-only, which keeps this service honest when the pipeline changes their shape.
"""

import logging

from studio_core import config
from studio_core.clients.aws import s3
from studio_core.errors import ForbiddenError, NotFoundError, ValidationError
from studio_core.services import catalog, keys

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

# The epoch, for a row carrying no timestamp at all. Sorting newest-first puts
# it last, which is where something we know nothing about belongs. Only a row
# written by hand can reach this — `catalog` stamps every write.
_UNDATED = ""


def clean_sort(raw: str | None) -> str:
    if raw in (None, ""):
        return DEFAULT_SORT
    if raw not in SORTS:
        raise ValidationError(f"sort must be one of {', '.join(sorted(SORTS))}")
    return raw


# ───────────────────────── locating a folder ─────────────────────────
#
# **`node` is the simple address and `prefix` is the expensive one**, which is
# the reverse of how it reads. A listing is a query on `pk = NODE#<parent>`, so
# an id is the thing it already needs; a path has to be walked from the library
# root one `GetItem` per segment before the listing can start. `prefix` survives
# because the SPA and every share link ever handed out are still paths of names
# — #313 moves them onto ids, and this walk goes with them.


def _segments(raw: str | None) -> list[str]:
    """The names in a slash-joined path, in order.

    No traversal rules and no root confinement, and neither is missing. Each
    segment is looked up as an exact `NAME#` sort key, and `keys.clean_name`
    refuses a slash, a `.`, a `..` and a control character on the way *in* — so
    no stored name can match one and `../elsewhere` is simply a name nothing is
    called. The scrubbing `keys.clean_prefix` did was there because the same
    text was about to become an S3 key. It is not one any more (#312).
    """
    return [segment for segment in (raw or "").split("/") if segment]


def _node_at(
    lib: str, raw_prefix: str | None, node_id: str | None, label: str = "prefix"
) -> dict:
    """The node a request names, by id or by name path — one or the other.

    **It was `_folder_at` and it never checked for a folder**, which is why it is
    now named for what it returns. `/api/asset` and `/api/text` address a *file*
    the same two ways since #432, and they resolve it here rather than repeating
    the walk — one description of "which node did this request mean" for all four
    read endpoints.

    **Both together is a 400 rather than a guess**, the same refusal
    `PATCH /api/nodes/<id>` makes about `name` and `parent`: the two can disagree,
    and picking one silently is how a listing shows a folder nobody asked for.
    `label` is the query parameter the caller actually sent — `prefix` on a
    listing, `key` on the two file routes — so the message names something the
    caller can find in their own URL.

    Membership is checked against the node's own `lib` and not against the
    library the request resolved, which is `routes/nodes`' rule and matters for
    the same reason — a node id is shareable, so the guard has to be the node's
    own answer. The path walk cannot reach another library at all, since it
    starts at this one's root; the check is uniform anyway so there is one rule
    rather than two.

    A path naming a *file* returns that file's node, whose child listing is
    empty. Forgiving on purpose, and the same answer the old prefix listing gave
    — `browse` is the read side, and a read that names nothing is empty rather
    than wrong.
    """
    if node_id and raw_prefix:
        raise ValidationError(f"send {label} or node, not both")

    if node_id:
        record = catalog.node(node_id)
    else:
        walked = catalog.library(lib)["root_node"]
        for name in _segments(raw_prefix):
            walked = catalog.child_by_name(walked, name)["node_id"]
        record = catalog.node(walked)

    if record["lib"] != lib:
        raise ForbiddenError(f"You are not a member of {record['lib']}.")
    return record


def _breadcrumbs(record: dict) -> list[dict]:
    """Ancestor trail for a folder, root first, each entry navigable.

    **Walks `parent_id` rather than splitting a prefix** (#311). The old form cut
    the string on `/` because the path *was* the S3 key; a name path is now a
    rendering of the tree rather than a location in it, so the tree is what is
    asked. The root is the node with no `parent_id` — the same missing pointer
    that makes it unrenamable — and it is the crumb that reads as `/`.

    **This costs one `GetItem` per level, sequentially**, because each parent's
    id is only known once its child has been read. Depth in this library is four
    or five, so that is four or five sub-millisecond reads; there is no batch
    that would help, since a batch needs the keys up front. The `prefix` form of
    a request pays it twice — once walking down to resolve the path and once
    walking back up — which is another reason `?node=` is the cheaper address.

    Each crumb carries the `id` of the node it names, for the same reason every
    row below does: a crumb is a navigation target, and one that could only be
    followed by re-resolving its path would be the last thing sending the SPA
    back to `/api/resolve`.
    """
    walked = record
    ancestors = [record]
    while walked.get("parent_id"):
        walked = catalog.node(walked["parent_id"])
        ancestors.append(walked)
    ancestors.reverse()

    # The root is the node with no `parent_id`, and it is the crumb named `/`
    # rather than by whatever the library called it — the library's name belongs
    # to `/api/libraries`, and a crumb reading "Library" would be a second name
    # for the place the SPA calls the root.
    trail = [{"id": ancestors[0]["node_id"], "name": "/", "prefix": ""}]
    prefix = ""
    for ancestor in ancestors[1:]:
        prefix = f"{prefix}{ancestor['name']}/"
        trail.append({"id": ancestor["node_id"], "name": ancestor["name"], "prefix": prefix})
    return trail


def _name_path(record: dict) -> str:
    """One node's slash-joined name path — the address every response calls `key`.

    **Composed by walking, never read off the row**, for the reason `_file_entry`
    gives: `path` names ancestors by *id* and `blob_key` is the attribute that
    must not leave. So a node addressed by `?node=` still answers with the same
    kind of string a node addressed by `?key=` was asked for, and neither answer
    leaks where the bytes actually sit.

    The root contributes no segment — it is the empty prefix everywhere else —
    so a file directly under it is just its own name. Same cost and same shape as
    `_breadcrumbs`, one `GetItem` per level; this returns the string rather than
    the trail because the two file routes have nothing to navigate.
    """
    names = [record["name"]]
    walked = record
    while walked.get("parent_id"):
        walked = catalog.node(walked["parent_id"])
        if walked.get("parent_id"):
            names.append(walked["name"])
    return "/".join(reversed(names))


# ───────────────────────── rows as listing entries ─────────────────────────


def _timestamp(record: dict) -> str:
    """The one date a row reports, and the one every order here sorts on.

    `updated_at`, because the field is called `last_modified` and that is what it
    means; `created_at` only for a row old enough to predate the pair. Using one
    value for both the display and the sort is deliberate — a listing ordered by
    a date it does not show is the kind of thing that reads as a bug forever.
    """
    return record.get("updated_at") or record.get("created_at") or _UNDATED


def is_abandoned_upload(record: dict) -> bool:
    """A row that names bytes which never arrived — an upload that stopped mid-way.

    **`"size" in record`, not `record.get("size")`.** A confirmed empty file has
    `size` 0 and a placeholder has it absent — `_attributes` drops `None` and
    keeps `0` — so membership tells them apart and truthiness does not. That
    distinction is the whole reason this is a function rather than an inline
    check somebody later "simplifies".

    `create_node` mints `blob_key` immediately, and `_file_entry` presigns any
    row carrying one. So without this an abandoned upload is **a tile the grid
    draws and cannot load** — which is what #442 reported and what
    `routes/nodes` claimed was impossible. That claim was true under #294, when
    a listing came from `ListObjectsV2` and an object that did not exist could
    not appear in one; #424 moved listings onto the catalog and nothing
    revisited it.

    **A row with no `blob_key` at all is a different thing and still lists.**
    Nothing signs for it, so it draws an item with no preview rather than a
    broken one — which is what it is, and `test_a_file_row_with_no_blob_lists_
    without_a_url` pins that on purpose. Only the combination is a defect: a key
    promised, and no bytes behind it.

    **A hidden row is not a collected one.** `catalog gc` deletes blobs no row
    names; this is a row no blob answers, and nothing collects it. Hiding it
    stops a user seeing a broken tile and leaves the row to accumulate — the
    lesser of the two, and #442 carries the rest.
    """
    return bool(record.get("blob_key")) and "size" not in record


def _file_entry(record: dict, prefix: str) -> dict:
    """One file row as a listing entry, presigned.

    **`key` is the name path, never `blob_key`.** That is `routes/nodes`' rule
    and it holds here for the same reason: prod stores `characters/<slug>/…`
    keys written years before the catalog beside `blobs/<node-id>` keys written
    after it, and both stay correct only while nothing outside `services.catalog`
    parses one. `path` is withheld for the weaker reason `_view` gives — it is a
    materialised index of ancestor ids that a move rebuilds.

    For everything written before the catalog the name path and the blob key are
    the same string, which is what lets the key-addressed write routes keep
    working until #316 retires them. They are not the same string for anything
    written since, and nothing here may assume they are.

    `size`, `content_type` and the timestamp come off the row (#311). `kind` and
    `language` are still classified from the extension, because `content_type`
    is what an uploader claimed and the extension is what the browser will
    actually try to decode.
    """
    name = record["name"]
    entry = {
        "id": record["node_id"],
        "key": f"{prefix}{name}",
        "name": name,
        "size": record.get("size", 0),
        "content_type": record.get("content_type"),
        "last_modified": _timestamp(record),
        "kind": keys.kind(name),
    }

    blob_key = record.get("blob_key")
    if blob_key:
        entry["url"] = s3.presign(blob_key)
    # No `url` at all when there is no blob: a placeholder whose bytes never
    # landed (#294 mints the row before the upload) has nothing to sign for, and
    # a signed URL onto a missing object is a broken tile rather than an absent
    # one.

    if entry["kind"] == "text":
        entry["language"] = keys.language(name)
    return entry


def _folder_entry(record: dict, prefix: str) -> dict:
    """One folder row as a listing entry.

    It carries `last_modified` now, and that is the retirement of a documented
    constraint rather than a new field for its own sake: a delimited listing
    returned common prefixes, a common prefix is not an object, and an object is
    the only thing S3 dates — so the date orders used to fall back to the
    folder's name and `docs/WEB_APP.md` warned against HEADing every prefix to
    invent one. A folder is a row now and is stamped like any other.
    """
    return {
        "id": record["node_id"],
        "prefix": f"{prefix}{record['name']}/",
        "name": record["name"],
        "last_modified": _timestamp(record),
    }


def _sort_records(records: list[dict], sort: str) -> None:
    """Order node records in place — files and folders, the same way.

    **The key tie-break is gone**, and it was load-bearing right up until it was
    not. S3's `LastModified` has one-second resolution and a run writes its whole
    output inside one second, so a date sort over a listing tied almost
    everywhere: `_sort_files` had to sort by key first and by date second, two
    passes over a stable sort, or `newest` handed back `frame_9, frame_8,
    frame_7` for every run. `catalog._now` stamps microseconds, so two rows
    written in the same second still order correctly and there is nothing left to
    break. Equal timestamps now mean equal instants rather than equal seconds,
    and Python's stable sort leaves those in the order the query returned them.
    """
    if sort == "name":
        records.sort(key=lambda record: record["name"].lower())
    elif sort == "name_desc":
        records.sort(key=lambda record: record["name"].lower(), reverse=True)
    else:
        records.sort(key=_timestamp, reverse=sort == "newest")


def _records_for(entries: list[dict]) -> list[dict]:
    """Full records for a folder's children, in the order they were listed.

    `catalog.children` returns the by-parent projection — `node_id`, `lib`,
    `kind`, `path`, `created_at` and the name — which has no `size`, no
    `content_type` and no `blob_key`, so a listing cannot be rendered from it
    alone. Those come from `catalog.records`: one query plus `ceil(n / 100)`
    batched reads. Widening the projection instead would make this one query and
    put a mutable copy of every file's metadata on a second item, which every
    rename and every text edit would then have to keep in step (#280).
    """
    full = catalog.records([entry["node_id"] for entry in entries])
    records = []
    for entry in entries:
        record = full.get(entry["node_id"])
        if record is None:
            # A folder listing a child whose record is not there. Reported from
            # the projection rather than dropped, for the reason
            # `routes/nodes.list_nodes` gives: a node hidden here is a node that
            # still exists and can still be opened by id. Logged because every
            # write in `services.catalog` is a transaction over both halves, so
            # one half alone means a row was written by hand.
            logger.warning("Listed child has no record: %s", entry["node_id"])
            record = entry
        records.append(record)
    return records


# ───────────────────────────── the endpoints ─────────────────────────────


def list_folder(
    lib: str,
    raw_prefix: str | None = None,
    raw_sort: str | None = None,
    *,
    node_id: str | None = None,
) -> dict:
    """Immediate contents of one folder, ready to render.

    **One query and one batched read** (#309), where this used to be a delimited
    `ListObjectsV2`. Folders and files come back in the same pass distinguished
    by `kind` — they are the same item type now — and the query returns
    name-ascending, which is two of the four sorts for free.

    A zero-byte folder marker cannot exist in a catalog, so nothing filters for
    one. That filter, and the "the prefix itself comes back as an object" filter
    beside it, were both artefacts of asking S3 what a folder was.
    """
    sort = clean_sort(raw_sort)
    folder = _node_at(lib, raw_prefix, node_id)
    records = _records_for(catalog.children(folder["node_id"]))

    # **The prefix is read back off the crumbs, never echoed from the request.**
    # Under `?node=` there was no path to echo, and under `?prefix=` the crumbs
    # are the normalised form of what was sent — so one source answers both, and
    # the two addresses cannot return different `prefix` values for one folder.
    breadcrumbs = _breadcrumbs(folder)
    prefix = breadcrumbs[-1]["prefix"]

    folders = [record for record in records if record["kind"] == catalog.KIND_FOLDER]
    files = [
        record
        for record in records
        if record["kind"] != catalog.KIND_FOLDER and not is_abandoned_upload(record)
    ]
    _sort_records(folders, sort)
    _sort_records(files, sort)

    entries = [_file_entry(record, prefix) for record in files]
    return {
        "prefix": prefix,
        "sort": sort,
        "breadcrumbs": breadcrumbs,
        "folders": [_folder_entry(record, prefix) for record in folders],
        "files": entries,
        "counts": {
            "folders": len(folders),
            "files": len(entries),
            "media": sum(1 for entry in entries if entry["kind"] in REEL_KINDS),
        },
    }


def reel_items(
    lib: str,
    raw_prefix: str | None = None,
    cursor: str | None = None,
    page_size: int | None = None,
    raw_sort: str | None = None,
    *,
    node_id: str | None = None,
) -> dict:
    """Every image and video beneath a folder, recursively, one page at a time.

    **Two enumerations, one for each shape of request** (#310). A reel from the
    library root is a `by-recent` query — hashed on `lib`, ranged on
    `created_at`, so the newest rows arrive first and a cut drops the oldest. A
    reel from anywhere else is a `by-path` `begins_with`, one query for a whole
    branch. Both are bounded by `config.max_folder_objects`, which replaces
    `STUDIO_MAX_WALK_OBJECTS` and the twenty-thousand-object S3 walk it bounded.

    **This is still fetch-then-sort, and it should be said plainly.** Sorting by
    date means the whole branch has to be known before a page can be cut from it,
    and `name` sorts are not an order either index offers, so the rows are read,
    filtered, sorted in memory and sliced. The cursor is an offset into that,
    not a `LastEvaluatedKey`. What improved is what is enumerated — rows rather
    than objects, with a real microsecond `created_at` rather than a
    one-second `LastModified` — not the complexity.

    Presigning still happens *after* the slice, so a request signs one page's
    worth of URLs rather than the branch's. Keep it that way.
    """
    sort = clean_sort(raw_sort)
    limit = _reel_page_size(page_size)
    offset = _reel_offset(cursor)

    folder = _node_at(lib, raw_prefix, node_id)
    breadcrumbs = _breadcrumbs(folder)
    prefix = breadcrumbs[-1]["prefix"]

    cap = config.max_folder_objects()
    base_path = catalog.child_path(folder)
    if folder.get("parent_id"):
        rows, truncated = catalog.branch(lib, base_path, cap)
    else:
        rows, truncated = catalog.recent(lib, cap)

    media = [
        record
        for record in rows
        if record["kind"] == catalog.KIND_FILE
        and not is_abandoned_upload(record)
        and keys.kind(record["name"]) in REEL_KINDS
    ]
    _sort_records(media, sort)

    window = media[offset : offset + limit]
    prefixes = _folder_prefixes(window, prefix, base_path, rows)
    items = [_file_entry(record, prefixes[record["node_id"]]) for record in window]

    next_offset = offset + len(window)
    return {
        "prefix": prefix,
        "sort": sort,
        "items": items,
        "total": len(media),
        # True when the *enumeration* was cut short, not the page — the caller
        # is showing a library that has more in it than this endpoint will admit
        # to, and should say so rather than imply the tail does not exist.
        "truncated": truncated,
        "next_cursor": str(next_offset) if next_offset < len(media) else None,
    }


def _folder_prefixes(
    window: list[dict], base_prefix: str, base_path: str, rows: list[dict]
) -> dict[str, str]:
    """The name path of each windowed row's own folder, keyed by node id.

    A row carries `path` — its ancestors as *ids* — and a client is owed names.
    The enumeration already read every folder in the branch, so the names are
    almost always in hand and this costs nothing; the exception is a truncated
    enumeration, where a surviving row's ancestor may have been cut, and that is
    one batched read rather than a walk per item.

    Only the window is resolved. Naming every row's folder would undo the whole
    point of slicing before presigning.
    """
    names = {record["node_id"]: record["name"] for record in rows}
    missing = {
        node_id
        for record in window
        for node_id in record["path"][len(base_path) :].split("/")
        if node_id and node_id not in names
    }
    if missing:
        names |= {
            node_id: record["name"]
            for node_id, record in catalog.records(sorted(missing)).items()
        }

    prefixes = {}
    for record in window:
        tail = [part for part in record["path"][len(base_path) :].split("/") if part]
        prefixes[record["node_id"]] = base_prefix + "".join(
            f"{names.get(node_id, node_id)}/" for node_id in tail
        )
    return prefixes


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


# ───────────────────────── the two file-at-a-time reads ─────────────────────
#
# `/api/asset` re-signs what a listing handed out; `/api/text` reads what
# `PATCH /api/text` writes back. Both take `?node=<id>` since #432, the way
# `/api/tree` and `/api/reel` took it in #424, and both together is a 400.
#
# **`?key=` does not mean the same thing on the two of them, and that is the one
# thing to know about this section.** On `/api/text` it is a *name path*, walked
# against the catalog exactly as `PATCH /api/text` walks it — that pairing was
# the whole of #432, and it is now symmetric. On `/api/asset` it is still a raw
# **S3 key**, because that route is also how the pipeline reads *shared*
# material: `phrasebook/wording.yaml` and the `config/pose/` plates belong to no
# character and no project, `catalog_seed` deliberately records no node for
# them, and `GET /api/resolve` 404s on them by design (see
# `pipeline/adapters/store.shared_read`). A name path cannot address a thing with
# no node, so the key-addressed form stays and `keys.clean_key` stays with it —
# which is why #312 could not take all four of the functions it expected to.


def _blob_at(lib: str, raw_path: str | None, node_id: str | None) -> dict:
    """The file node one of these two routes names, with bytes behind it.

    Three refusals, and each is a different answer to a different mistake: a
    folder is a 400 because the node exists and the request does not apply to it
    (`GET /api/nodes/<id>/download-url`'s rule, kept identical); a placeholder
    minted by #294 whose upload never landed is a 404 naming the file, because
    there is genuinely nothing to read; and a name path that names nothing is
    `catalog.child_by_name`'s own 404.
    """
    record = _node_at(lib, raw_path, node_id, "key")
    if record["kind"] != catalog.KIND_FILE:
        raise ValidationError("a folder has no contents to read")
    if not record.get("blob_key"):
        raise NotFoundError(record["name"])
    return record


def asset_url(
    lib: str, raw_key: str | None, disposition: str | None, *, node_id: str | None = None
) -> dict:
    """A fresh presigned URL for one object.

    Used both to drive downloads and to re-sign a URL the browser found expired,
    which is why it exists separately from the listing endpoints.

    **`?node=` is the address the SPA uses and the only one that works for
    anything written since the catalog.** A row minted by #294 keeps its bytes at
    `blobs/<node-id>`, which no client is ever handed, so signing the string a
    listing called `key` would sign a key that does not exist. Under `?key=` this
    still signs what it was given — see the section comment above for the shared
    material that needs it.

    `size` and `content_type` come from S3 in both branches rather than off the
    row, because this endpoint's job is to prove the bytes are there before it
    signs for them.
    """
    if disposition not in (None, "", "inline", "attachment"):
        raise ValidationError("disposition must be 'inline' or 'attachment'")

    if node_id:
        # `raw_key` is handed on rather than ignored: sending both is the 400
        # `_node_at` makes, and swallowing one here would answer for a request
        # that named two different things.
        record = _blob_at(lib, raw_key, node_id)
        key, name, blob_key = _name_path(record), record["name"], record["blob_key"]
    else:
        # A raw S3 key, and the last query string in the service that becomes one.
        key = blob_key = keys.clean_key(raw_key)
        name = keys.basename(key)

    # HEAD before signing so a mistyped key is a clean 404 rather than a URL that
    # only fails once the browser follows it.
    metadata = s3.head(blob_key)

    return {
        "key": key,
        "name": name,
        # Classified from the *name*, never from `content_type`, for
        # `_file_entry`'s reason: the header is what an uploader claimed and the
        # extension is what the browser will actually try to decode.
        "kind": keys.kind(name),
        "size": metadata.get("ContentLength", 0),
        "content_type": metadata.get("ContentType"),
        "expires_in": config.presign_ttl_seconds(),
        "url": s3.presign(blob_key, disposition=disposition or "inline", filename=name),
    }


def text_object(lib: str, raw_key: str | None, *, node_id: str | None = None) -> dict:
    """An object's contents as text, for the viewer and the editor behind it.

    Serving this through the API rather than letting the viewer fetch the
    presigned URL keeps it on one authenticated same-origin request — a
    cross-origin `fetch` to S3 would need CORS on a bucket this service does not
    own and must not modify.

    **This and `PATCH /api/text` address one node by the same two routes now**
    (#432). Until this change the save resolved a name path and the read did a
    `GetObject` on the string it was handed, so the pair agreed only for material
    written before the catalog: a file the editor could save was a file the
    editor could not re-open. Both walk the catalog, so a rename cannot separate
    them and a `blobs/<node-id>` blob is reachable from both.
    """
    record = _blob_at(lib, raw_key, node_id)
    name = record["name"]
    if keys.kind(name) != "text":
        raise ValidationError("key is not a viewable text file")

    cap = config.max_text_bytes()
    # One byte over the cap tells us it was truncated without reading it all.
    body = s3.get_body(record["blob_key"], cap + 1)
    truncated = len(body) > cap
    if truncated:
        body = body[:cap]

    return {
        "key": _name_path(record),
        "name": name,
        "language": keys.language(name),
        "truncated": truncated,
        "content": body.decode("utf-8", errors="replace"),
    }
