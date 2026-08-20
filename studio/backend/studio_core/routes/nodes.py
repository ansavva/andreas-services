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

## Why the writes are here and not in `routes/manage.py`

#293 named `manage.py`, and that would put two different addressing schemes in
one file. Every route in `manage` takes an S3 key or a prefix; every route here
takes a node id. They overlap until #309 retires the first, and during that
overlap the one thing a reader must never have to work out is which storage a
handler is talking to — which is the same reason the read routes were split out
in the first place. The verbs moved; the split did not.

## Three rules hold across all three read routes

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

from studio_core import config
from studio_core.clients.aws import s3
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


def _body() -> dict:
    """The JSON body, or an empty dict.

    `silent=True` so a malformed body surfaces as the missing-field
    `ValidationError` below rather than Flask's generic parse failure — a 400
    naming the field beats a 400 naming nothing. Same helper, same reason, as
    `routes/manage.py`.
    """
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


@bp.post("/nodes")
def create_node():
    """Create a folder, or a file pointing at a blob that already exists.

    **The parent is what authorises this**, not the library the request
    resolved: the node being created has no `lib` yet, and the parent's is the
    one it will inherit — `catalog.create_node` reads it off the parent rather
    than taking it as an argument, so that a node cannot be listed in one
    library's subtree and owned by another.

    `kind` is `folder` or `file`, and a file needs `blob_key`. That asymmetry is
    the whole definition of a folder (#280: a node with no blob), and it is
    enforced in `services.catalog` rather than here so the CLI gets the same
    refusal when it writes through the API (#309).
    """
    body = _body()
    parent_id = body.get("parent")
    if not parent_id:
        raise ValidationError("parent is required")

    memberships = _memberships()
    parent = catalog.node(parent_id)
    _member_of(parent["lib"], memberships)

    record = catalog.create_node(
        parent_id,
        body.get("name"),
        body.get("kind"),
        blob_key=body.get("blob_key"),
        size=body.get("size"),
        content_type=body.get("content_type"),
    )
    return jsonify(_view(record)), 201


@bp.patch("/nodes/<node_id>")
def update_node(node_id: str):
    """Rename a node (`name`) or move it (`parent`) — one or the other.

    **Sending both is a 400 rather than a guess**, and refusing is the point.
    On the S3 side the two are different routes, and `keys.clean_name` refuses a
    slash so a rename cannot become a move by punctuation. Here they are two
    fields on one verb, so the separation has to be stated: a request that asks
    for both has two plausible orderings with different outcomes when the
    destination already holds that name, and picking one silently is how a file
    ends up somewhere nobody looked.

    A name collision is a transaction condition failure and comes back **409**,
    which is what tells the UI to keep the rename field open rather than closing
    it and reporting success.
    """
    body = _body()
    name = body.get("name")
    parent_id = body.get("parent")
    if name is not None and parent_id is not None:
        raise ValidationError("send name or parent, not both")
    if name is None and parent_id is None:
        raise ValidationError("send name to rename, or parent to move")

    memberships = _memberships()
    record = catalog.node(node_id)
    _member_of(record["lib"], memberships)

    if name is not None:
        return jsonify(_view(catalog.rename_node(node_id, name))), 200

    # **The destination is not re-checked here**, and that is deliberate rather
    # than an omission. `catalog.move_node` already refuses a destination in a
    # different library, so a destination that survives it is in the same one as
    # the node — which was membership-checked above. Repeating the rule here
    # would be a second description of it, and the one that drifts.
    #
    # Moving a node to another library is a transfer (#325), not a move: it
    # carries blob keys, share links and membership implications with it.
    return jsonify(_view(catalog.move_node(node_id, parent_id))), 200


@bp.delete("/nodes/<node_id>")
def delete_node(node_id: str):
    """Delete a node and everything beneath it, rows first and then blobs.

    **That order is the recoverable one.** An orphan blob is invisible to every
    reader and collectable later; a row pointing at a blob that is gone is a
    broken tile in the grid, which is the failure a user sees. So if the second
    half fails, what is left is the harmless kind of inconsistent.

    **This is safe only while no two rows share a `blob_key`.**
    `catalog.delete_node` says so itself and declines to answer whether a blob
    is still referenced — there is no index on `blob_key` and the question is
    not cheap. Nothing creates a shared key today: copy-on-write copies are
    #334, in the Deferred milestone. **#334 has to revisit this**, because the
    day a copy shares a key, deleting one row here deletes the other's bytes.

    The subtree bound is `catalog.subtree`'s and it refuses rather than
    truncates — a half-finished delete reporting success is precisely what a
    limit would produce.
    """
    memberships = _memberships()
    record = catalog.node(node_id)
    _member_of(record["lib"], memberships)

    result = catalog.delete_node(node_id)
    if result["blob_keys"]:
        s3.delete(result["blob_keys"])
    # `blob_keys` is not returned. It is the internal half of a record for the
    # reason `_view` exists, and a client that received one would eventually
    # parse it.
    return jsonify({"id": result["node_id"], "deleted": result["deleted"]}), 200


@bp.get("/nodes/<node_id>/download-url")
def download_url(node_id: str):
    """A fresh presigned GET for one node's blob.

    **The id-addressed twin of `/api/asset`**, and it exists separately for the
    same reason the rest of this file does: `/api/asset` takes a key and this
    takes a node id, and a client that has an id should never have to learn a
    key to fetch bytes — that coupling is what the catalog was built to remove.

    **Signed fresh on every call rather than returned by the listing routes.**
    A presigned URL dies with the credentials that signed it, not with the
    `ExpiresIn` it was asked for: the Lambda's role credentials rotate, and a URL
    outlives them by nothing. So `list_nodes` deliberately hands out no URLs at
    all, and a client re-signs here when one stops working — the behaviour
    `config.presign_ttl_seconds` documents and the frontend already relies on
    for `/api/asset`.

    `disposition=attachment` is what makes a download download. The URL points at
    S3, so it is cross-origin to the app, and a cross-origin `<a download>` is
    ignored by browsers — signing `response-content-disposition` into the URL is
    the only thing that works. The filename comes from the node's `name`, which
    is the one a person recognises; `blob_key` is meaningless to them and, for
    everything written before the catalog, does not resemble the name at all.

    A folder has no blob and is a **400** rather than a 404: the node is there,
    the request does not apply to it.
    """
    memberships = _memberships()
    record = catalog.node(node_id)
    _member_of(record["lib"], memberships)

    blob_key = record.get("blob_key")
    if not blob_key:
        raise ValidationError("a folder has nothing to download")

    disposition = request.args.get("disposition") or "inline"
    if disposition not in ("inline", "attachment"):
        raise ValidationError("disposition must be 'inline' or 'attachment'")

    # `head` before signing, so a record pointing at a blob that is not there is
    # a clean 404 here rather than a URL that only fails once the browser follows
    # it. The same order `browse.asset_url` uses, for the same reason.
    metadata = s3.head(blob_key)
    url = s3.presign(blob_key, disposition=disposition, filename=record["name"])

    return jsonify(
        {
            "id": node_id,
            "name": record["name"],
            "url": url,
            "expires_in": config.presign_ttl_seconds(),
            # From S3 rather than from the record: the object is the thing being
            # fetched, and a row whose `size` drifted from the bytes would send a
            # client a number the download then contradicts.
            "size": metadata.get("ContentLength", 0),
            "content_type": metadata.get("ContentType"),
        }
    ), 200


@bp.post("/nodes/<node_id>/upload-url")
def upload_url(node_id: str):
    """Sign a PUT for one node's blob. Call `confirm-upload` once it lands.

    **This is the reversal `docs/WEB_APP.md` and `modules/compute/main.tf` both
    said would have to be argued separately (#294), and this is the argument.**
    Until now no path in this service could create an object out of bytes a
    caller supplied: `PutObject` wrote zero-byte folder markers and overwrote
    text files that already existed, and `CopyObject` did the rest — every write
    was either something already in the bucket or nothing at all. That property
    is now gone, deliberately, and these are the bounds that replace it.

    **The bytes never transit the Lambda**, which is what makes this possible at
    all: an upload through the API would blow the 6 MB request limit on any
    video. It also means the API never sees what is stored.

    **The grant is one object, one length, one type, once.** `content-length` and
    `content-type` are signed headers, so a client sending different values fails
    signature validation and writes nothing — an oversized body is refused by S3
    rather than discovered afterwards, which is the constraint #294 asks for. The
    key is signed too, so a URL issued for this node cannot be redirected at
    another object. The TTL is `config.upload_ttl_seconds`, shorter than a read
    URL's and well under the Lambda credential lifetime.

    **Still no multipart grant.** `max_upload_bytes` is S3's single-PUT ceiling
    rather than a policy number: past it a single `PutObject` is impossible, and
    multipart is a separate decision again.

    The row is not touched here. The node stays a placeholder — a key with no
    object behind it — until `confirm-upload` runs. A client that signs a URL and
    never uses it has changed nothing.
    """
    body = _body()
    size = body.get("size")
    content_type = body.get("content_type")
    # `isinstance(size, bool)` because `True` is an `int` in Python and a body of
    # `{"size": true}` would otherwise sign a one-byte upload.
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ValidationError("size must be a non-negative integer")
    if size > config.max_upload_bytes():
        raise ValidationError(
            f"size must be at most {config.max_upload_bytes()} bytes — "
            "there is no multipart upload"
        )
    if not isinstance(content_type, str) or not content_type:
        raise ValidationError("content_type is required")

    memberships = _memberships()
    record = catalog.node(node_id)
    _member_of(record["lib"], memberships)
    blob_key = _api_blob_key(record)

    return jsonify(
        {
            "id": node_id,
            "url": s3.presign_put(blob_key, content_length=size, content_type=content_type),
            "expires_in": config.upload_ttl_seconds(),
            # Echoed because they are not advisory: the PUT must carry exactly
            # these two or the signature fails.
            "headers": {"Content-Length": str(size), "Content-Type": content_type},
        }
    ), 200


@bp.post("/nodes/<node_id>/confirm-upload")
def confirm_upload(node_id: str):
    """Finalise a placeholder once its bytes have landed.

    **`HeadObject` first, and the row is written from what it returns** rather
    than from anything the client says. The client already declared a size when
    it asked for the URL; repeating it here would trust the same claim twice
    instead of checking it once. S3 knows what it stored.

    Until this runs the node is a placeholder. A client that uploads and never
    confirms leaves an object whose row does not know its size — the state a
    collector would tidy. **There is no `catalog gc`**: #294 assumed one and it
    does not exist, so today that is a hand cleanup. Worth knowing before this
    route is driven at volume.
    """
    memberships = _memberships()
    record = catalog.node(node_id)
    _member_of(record["lib"], memberships)
    blob_key = _api_blob_key(record)

    # 404 when the object is not there — the upload did not happen, or did not
    # finish. Distinguishable from a node that does not exist, because that is a
    # 404 raised earlier, off the record.
    metadata = s3.head(blob_key)
    updated = catalog.set_blob(
        node_id,
        blob_key,
        size=metadata.get("ContentLength", 0),
        content_type=metadata.get("ContentType"),
    )
    return jsonify(_view(updated)), 200


def _api_blob_key(record: dict) -> str:
    """The key both upload routes work on, or a refusal.

    Shared so the two cannot disagree about which objects are writable through a
    signature — a distinction a signed URL makes permanent the moment it is
    handed out.

    The key is the node's own, never one the caller named: a caller-supplied key
    would turn this into a signature for an arbitrary object in the bucket, which
    is the entire thing being avoided. A node whose `blob_key` is anything else
    predates the catalog (#309), and overwriting bytes that were written before
    this table existed is not what these routes are for.
    """
    if record["kind"] != catalog.KIND_FILE:
        raise ValidationError("only a file can carry a blob")
    blob_key = catalog.blob_key_for(record["node_id"])
    if record.get("blob_key") != blob_key:
        raise ValidationError("this node's blob was not written through the API")
    return blob_key


# ──────────────────────────── recording a run ────────────────────────────
#
# `POST /api/runs` is the CLI's entry point (#309), not the app's. The pipeline
# produces a run folder, two small JSON documents and some number of large
# outputs; this records the shape of that in the catalog so the browser can see
# it, and hands back an upload URL per output so the bytes go straight to S3.


@bp.post("/runs")
def record_run():
    """Record a run: its folder, its documents, and placeholders for its outputs.

    **The documents are stored as bytes and never decoded**, which is the rule
    `docs/WEB_APP.md` has held since before the catalog: the pipeline owns the
    shape of `request.json` and changes it freely, so the moment this parsed one
    into typed fields it would become a liar. They arrive as strings, they are
    encoded to UTF-8, and they are written verbatim. Nothing here reads a key
    inside them, and `GET /api/text` hands them back byte-identical.

    **Documents inline, outputs by presigned PUT**, and the split is by size
    rather than by kind. A `result.json` is a few hundred bytes and travels fine
    in this request; a video would blow the Lambda's 6 MB limit, so each output
    gets a placeholder node and a URL from #294 that the caller PUTs to directly.
    The response carries those URLs so recording a run is one round trip rather
    than one per file.

    **The run folder keeps its `<ts>_<slug>` name.** It sorts chronologically as
    a string and the UI depends on that; this route does not parse it either, and
    deliberately does not derive a timestamp from it.

    Not transactional across the whole run, and it cannot be: the documents are
    S3 writes and the nodes are DynamoDB writes. A failure part-way leaves a run
    folder holding fewer children than it should, which is a visible,
    re-runnable state — the same trade `catalog.delete_node` makes deliberately.
    """
    body = _body()
    parent_id = body.get("parent")
    name = body.get("name")
    documents = body.get("documents") or {}
    outputs = body.get("outputs") or []

    if not parent_id:
        raise ValidationError("parent is required")
    if not isinstance(documents, dict):
        raise ValidationError("documents must be an object of name -> contents")
    if not isinstance(outputs, list):
        raise ValidationError("outputs must be a list")

    total = sum(len(text.encode()) for text in documents.values() if isinstance(text, str))
    if total > config.max_text_bytes():
        raise ValidationError(
            f"documents must total at most {config.max_text_bytes()} bytes — "
            "upload anything larger as an output"
        )

    memberships = _memberships()
    parent = catalog.node(parent_id)
    _member_of(parent["lib"], memberships)

    run = catalog.create_node(parent_id, name, catalog.KIND_FOLDER)

    written = []
    for document_name, text in documents.items():
        if not isinstance(text, str):
            raise ValidationError(f"'{document_name}' must be a string")
        written.append(_write_document(run["node_id"], document_name, text))

    placeholders = []
    for entry in outputs:
        if not isinstance(entry, dict):
            raise ValidationError("each output must be an object")
        placeholders.append(_placeholder_for(run["node_id"], entry))

    return jsonify(
        {"run": _view(run), "documents": written, "outputs": placeholders}
    ), 201


def _write_document(run_id: str, name: str, text: str) -> dict:
    """One document: a node, its bytes, and the size read back off the write.

    The node is created first because its id is what names the key — the same
    ordering the upload routes use, for the same reason. `set_blob` then records
    the length that was actually encoded rather than `len(text)`, which counts
    characters and would be wrong for anything non-ASCII.
    """
    node = catalog.create_node(run_id, name, catalog.KIND_FILE)
    blob_key = catalog.blob_key_for(node["node_id"])
    payload = text.encode()
    # `text/plain` and not `application/json`, deliberately: the frontend shows
    # these as text and never decodes them, and a JSON content type is an
    # invitation to a browser — or a future contributor — to do exactly that.
    s3.put_text(blob_key, payload, "text/plain; charset=utf-8")
    return _view(
        catalog.set_blob(
            node["node_id"],
            blob_key,
            size=len(payload),
            content_type="text/plain; charset=utf-8",
        )
    )


def _placeholder_for(run_id: str, entry: dict) -> dict:
    """One output: a placeholder node and the URL its bytes go to.

    Signed here rather than left to a second call, so recording a run is one
    round trip. The same bounds as `upload-url` apply because it is the same
    signature: one key, one exact length, one content type.
    """
    size = entry.get("size")
    content_type = entry.get("content_type")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ValidationError("each output needs a non-negative integer size")
    if size > config.max_upload_bytes():
        raise ValidationError(f"an output must be at most {config.max_upload_bytes()} bytes")
    if not isinstance(content_type, str) or not content_type:
        raise ValidationError("each output needs a content_type")

    node = catalog.create_node(run_id, entry.get("name"), catalog.KIND_FILE)
    blob_key = catalog.blob_key_for(node["node_id"])
    return {
        **_view(node),
        "upload_url": s3.presign_put(blob_key, content_length=size, content_type=content_type),
        "expires_in": config.upload_ttl_seconds(),
        "headers": {"Content-Length": str(size), "Content-Type": content_type},
    }
