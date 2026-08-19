"""The catalog's read surface: list a folder, fetch a node, resolve a name path.

Its own blueprint rather than three more routes in `routes/browse.py`, and the
distinction is not tidiness. `browse` addresses the bucket — every route there
takes an S3 key or prefix, and what it returns is assembled by listing objects.
These routes address the *catalog*, where a node has an id, a name and a parent,
and an S3 key is an opaque attribute nothing outside `services.catalog` ever
sees. The two surfaces answer the same questions from different sources and
overlap for as long as the migration takes (#309 onwards), so keeping them in
separate files is what stops a reader from having to work out which storage a
given handler is talking to.

## Three rules hold across all three routes

**`blob_key` never leaves.** `_view` is an **allowlist**, not a `pop`. That
choice is the mechanism: a denylist would leak the next internal attribute
anybody adds to a record, and it would leak it on the day it was added rather
than on the day someone noticed. The reason it matters is in `services.catalog`
— prod holds keys written years before the table existed alongside
`blobs/<node_id>` keys written after it, and both stay correct forever precisely
because no client can parse them. Hand a client one and someone will split it on
`/`, and the coupling the catalog was built to remove comes straight back.

**Every response is membership-checked against the node's `lib`.** Not against
the id the caller named, and not against a library the request asserted — the
node itself says which library it belongs to, and that is the value checked. A
node id is a v4 UUID, so this is not a guard against enumeration; it is the
guard against a *shared* id, which is the realistic case once a library has more
than one member and someone pastes a link.

**A missing node is 404 before the membership check can run**, because the
record is what names the library. Deliberate, and cheap: an id nobody was given
cannot be guessed, so the difference between "no such node" and "not yours" is
information an attacker has no way to reach.

## What comes from `before_request` (#351)

`g.caller_sub` and `g.library` are set on every request before any route here
runs, so nothing in this file verifies a token or reads a header to decide which
library a request is about. `/api/resolve` — the one route with no node to take
a library from — reads `g.library`, which is the hook's three cases resolved:
the `X-Studio-Library` header, a sole membership, or a refusal. Having a second
description of that rule here is how the two would drift apart.

`_memberships` is still a read per request, because the hook keeps only the
library it resolved and not the rows it resolved it from. That is one query on
one partition (`USER#<sub>`), and it is the check the *node* is authorised
against — `g.library` answers a different question, and is not a substitute for
it.
"""

import logging

from flask import Blueprint, g, jsonify, request

from studio_core.errors import ForbiddenError, NotFoundError, ValidationError
from studio_core.services import catalog

logger = logging.getLogger(__name__)

bp = Blueprint("nodes", __name__, url_prefix="/api")

# What a node looks like to a client, and the entire list of it.
#
# `blob_key` is absent for the reason in the module docstring. `path` is absent
# for a different one: it is a materialised list of ancestor ids that exists so a
# subtree can be read with one query, it is rebuilt by a move, and a client that
# consumed it would be depending on an index this service reserves the right to
# rebuild. `parent_id` is the authoritative answer to the same question and is
# here.
VIEW_FIELDS = (
    "lib",
    "parent_id",
    "name",
    "kind",
    "size",
    "content_type",
    "created_at",
    "updated_at",
)


def _view(record: dict) -> dict:
    """One node record as this API reports it.

    `id` rather than `node_id`, matching `/api/libraries`: outside
    `services.catalog` a node is a thing with an id. Absent attributes are
    dropped rather than sent as null — a folder has no `size` and no
    `content_type`, and "the key is not there" is the same thing the catalog
    stores and one fewer state for a client to handle.
    """
    view = {"id": record["node_id"]}
    view.update({field: record[field] for field in VIEW_FIELDS if record.get(field) is not None})
    return view


def _memberships() -> list[str]:
    """The libraries the caller is in, by id.

    `g.caller_sub` is `before_request`'s, which raises `AuthError` — 401 — on a
    missing, malformed or unverifiable token, so there is no unauthenticated
    path past this line and the token is verified once per request.
    """
    return [membership["lib"] for membership in catalog.libraries_for(g.caller_sub)]


def _member_of(lib: str, memberships: list[str]) -> None:
    """Refuse unless the caller is in the library the node says it belongs to."""
    if lib not in memberships:
        raise ForbiddenError(f"You are not a member of {lib}.")


@bp.get("/nodes")
def list_nodes():
    """The children of one folder, name-ascending.

    **One query plus a batched read, and the batch is the interesting part.**
    `catalog.children` reads the by-parent items, whose projection is
    `node_id, lib, kind, path, created_at` — no `size`, no `content_type`. Those
    are fetched with `catalog.records`, which is `ceil(n / 100)` more round
    trips. Widening the projection instead would make this one query and put a
    mutable copy of every file's metadata on a second item, which every rename
    and every text edit would then have to keep in step (#309).

    A bare array, like `/api/libraries`, and folders and files interleaved
    rather than split: `kind` already distinguishes them, and a client that wants
    folders first is sorting a list it has, not asking for a different shape. The
    order is free — DynamoDB returns a partition sorted by sort key, and the sort
    key is the name.
    """
    parent_id = request.args.get("parent")
    if not parent_id:
        raise ValidationError("parent is required")

    memberships = _memberships()
    # Read before the listing rather than after, because the parent is what
    # names the library: an empty folder's children carry no `lib` to check, so
    # a listing authorised from its own results would authorise nothing at all
    # for exactly the folders that have nothing in them. This also turns a
    # parent that does not exist into the 404 it should be.
    parent = catalog.node(parent_id)
    _member_of(parent["lib"], memberships)

    entries = catalog.children(parent_id)
    full = catalog.records([entry["node_id"] for entry in entries])

    views = []
    for entry in entries:
        record = full.get(entry["node_id"])
        if record is None:
            # A folder listing a child whose record is not there. Reported from
            # the projection rather than dropped, for the reason
            # `routes/libraries.py` gives about a dangling membership: a node
            # hidden here is a node that still exists and can still be opened by
            # id. Logged because every write in `services.catalog` is a
            # transaction over both halves, so one half alone means a row was
            # written by hand.
            logger.warning(
                "Folder %s lists a child with no record: %s", parent_id, entry["node_id"]
            )
            record = entry
        views.append(_view(record))
    return jsonify(views), 200


@bp.get("/nodes/<node_id>")
def get_node(node_id: str):
    """One node's record, by id."""
    memberships = _memberships()
    record = catalog.node(node_id)
    _member_of(record["lib"], memberships)
    return jsonify(_view(record)), 200


@bp.get("/resolve")
def resolve():
    """A slash-joined name path to the node it names, walked from the library root.

    **This is what keeps the CLI and the old share links name-addressed.** Every
    URL this service has ever handed out is a path of names, and every command
    the pipeline runs names a subject and a project rather than an id. Neither
    has to learn ids to keep working; they ask here.

    **Splitting on `/` is unambiguous, and by construction rather than by
    convention.** `keys.clean_name` refuses a slash in a name, so no stored name
    can contain a separator and no escaping is needed on either side.

    **An absent or empty path is the library root**, which is the one node a
    client cannot otherwise reach: `/api/libraries` deliberately returns id, name
    and role and not the root node, so "where do I start" has to be answerable
    somewhere and this is the route whose whole job is turning a location into an
    id.

    No membership check on the result, because there is nothing left to check:
    the walk starts at a library resolved from the caller's own memberships, and
    every step is a child of the step before it. A node reached this way is in
    that library or the walk would not have reached it.
    """
    # `g.library` and not a membership read: this is the one route with no node
    # to take a library from, so the library is the one `before_request`
    # resolved — the header, a sole membership, or the refusal it already
    # raised. Nothing is checked again here because nothing new was named.
    root_id = catalog.library(g.library)["root_node"]

    path = request.args.get("path") or ""
    walked: list[str] = []
    node_id = root_id
    for name in [segment for segment in path.split("/") if segment]:
        walked.append(name)
        try:
            node_id = catalog.child_by_name(node_id, name)["node_id"]
        except NotFoundError as error:
            # Re-raised with everything walked so far, so the 404 says which
            # segment was the first one missing rather than only naming it — the
            # difference between "no such object: output" and a message that
            # points at the folder the typo is in.
            raise NotFoundError("/".join(walked)) from error

    return jsonify(_view(catalog.node(node_id))), 200
