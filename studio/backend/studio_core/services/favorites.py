"""Favorites: the pictures and clips one person picked out, and the screen of them.

## A favorite belongs to a PERSON, not to a library and not to a file

A tag is a fact about the picture — `face` is true of it whoever is looking —
so it lives on the node and everyone in the library sees it. A favorite is the
opposite: it is a fact about the person, and two members of one library are
entitled to disagree about it completely. So it is a row in the caller's own
`USER#<sub>` partition (`services/catalog.py` has the shape), never an attribute
on the node, and nothing here can read or change anybody else's.

**That is also why this is not a tag called `favorite`.** The vocabulary in
`services/tags.py` is shared, derived and library-wide; a shared favorite is a
different feature nobody asked for, and finding one would have cost a walk of
the whole library — see below.

## Images and video, and nothing else

`POST /api/favorites/<node>` refuses a folder and refuses a text file. The
screen this feeds is a grid of media, and a favorite that cannot be drawn on it
is a row that exists to disappoint whoever made it. It is the same set the
sparse `reel` index covers, named from the same constant — `browse.REEL_KINDS`
— so the two cannot drift into two answers to "what is media".

## What this costs, which is the reason it is built this way

The Recent grid that used to open the app was retired because twelve tiles cost
an enumeration of the whole library: `by-path` reads a branch, and a home screen
is not worth a branch. A favorites grid must not repeat that.

It does not. One query on one partition returns exactly the caller's picks —
bounded by the number of favorites, which is the number of things being shown —
then `ceil(n / 100)` batched reads hydrate them and the *page* is presigned.
Nothing walks the tree, and nothing is read that is not on its way to the
screen.

## A favorited file that has been deleted

A favorite points at a node id, and anybody in the library can delete the node.
The row survives it, because it is in a partition the deleter cannot address:
finding every member's favorites for one node is answerable (`by-sk` on
`sk = FAV#<lib>#<node>`) but doing it inside a delete would put a fan-out write
in the path of every delete, to collect a row that costs nothing to leave.

So a dead pointer is **skipped on the way out and not collected**, which is
`browse.is_abandoned_upload`'s bargain about a placeholder row and the same
trade: hiding it stops somebody seeing a broken tile, and the row accumulates.
The counts this reports are of live favorites, so a grid never claims a number
it cannot draw.
"""

import logging

from studio_core import config
from studio_core.errors import ValidationError
from studio_core.services import browse, catalog, keys

logger = logging.getLogger(__name__)

#: The kinds a favorite may name. `browse`'s, not a second list of the same two
#: words — what the reel can draw is what this grid can draw.
FAVORITE_KINDS = browse.REEL_KINDS


def ids(sub: str, lib: str) -> list[str]:
    """Every node this caller has favorited in this library, newest first.

    **Not hydrated, not presigned, and that is what it is for.** The app draws a
    heart on tiles all over the browser, the viewer and the run pages, and the
    only thing it needs to draw one is whether an id is in this set. Answering
    that per tile would be a request per tile; answering it once is this.

    Dead pointers are included here, deliberately: this is the set of rows, and
    a heart that reads as filled on a file that still exists is exactly right.
    The hydrated listing is where a pointer has to resolve to something
    drawable.
    """
    return [row["node_id"] for row in catalog.favorites(sub, lib)]


def listing(sub: str, lib: str, *, cursor: str | None, page_size) -> dict:
    """The favorites grid: one page of media, newest pick first.

    Hydrate, filter, then slice, then presign — `browse.entries`' order and for
    its reasons. `total` counts what survived the filters rather than what the
    query returned, so a grid saying "40" can draw forty.
    """
    limit = browse.clean_page_size(page_size)
    offset = browse.clean_cursor(cursor)

    rows = catalog.favorites(sub, lib)
    cap = config.max_folder_objects()
    truncated = len(rows) > cap
    rows = rows[:cap]

    found = catalog.records([row["node_id"] for row in rows])
    kept = []
    for row in rows:
        record = found.get(row["node_id"])
        if record is None:
            # The node was deleted out from under the favorite. See the module
            # docstring: skipped, not collected.
            continue
        if record["lib"] != lib or record["kind"] != catalog.KIND_FILE:
            continue
        if browse.is_abandoned_upload(record):
            continue
        kept.append((row, record))

    window = kept[offset : offset + limit]
    entries = [
        {**entry, "favorited_at": row["favorited_at"]}
        for entry, (row, _record) in zip(
            browse.file_entries([record for _row, record in window]), window
        )
    ]

    next_offset = offset + len(window)
    return {
        "entries": entries,
        "total": len(kept),
        # True when there are more favorites than one read admits — the same
        # word `browse.entries` uses, about the enumeration and never the page.
        "truncated": truncated,
        "next_cursor": str(next_offset) if next_offset < len(kept) else None,
    }


def add(sub: str, record: dict) -> dict:
    """Favorite one file, for this caller, in the library the FILE says it is in.

    **The node's own `lib`, never the request's.** A node id is shareable and
    `routes/support` checks membership against the record's answer, so filing
    the favorite anywhere else would put a row in a partition the listing for
    that library never reads.
    """
    kind = _drawable_kind(record)
    logger.debug("Favorite %s (%s)", record["node_id"], kind)
    return catalog.add_favorite(sub, record["lib"], record["node_id"])


def remove(sub: str, record: dict) -> None:
    """Unfavorite one node. No kind check: taking something off is always allowed."""
    catalog.remove_favorite(sub, record["lib"], record["node_id"])


def _drawable_kind(record: dict) -> str:
    """What this node is, or the refusal that says why it cannot be favorited."""
    if record["kind"] != catalog.KIND_FILE:
        raise ValidationError("a folder cannot be favorited")
    kind = keys.kind(record["name"])
    if kind not in FAVORITE_KINDS:
        raise ValidationError(
            f"only an image or a video can be favorited — this is {kind}"
        )
    if browse.is_abandoned_upload(record):
        raise ValidationError("this file's upload never finished")
    return kind
