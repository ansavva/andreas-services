"""The file layer: list, read, create, rename, move, copy, delete, upload, edit.

**Ids only.** Every route here takes a node id, and the name-path routes that
used to sit beside them in `routes/manage.py` are gone — `/api/folder`,
`/api/object`, `/api/objects/*` and `PATCH /api/text?key=`. What kept them alive
was that every share link this service had ever issued was a path of names; ids
in URLs everywhere is what retired them, and the whole of `manage.py` went with
the second addressing scheme rather than staying as a file a reader had to work
out the address convention of.

`GET /api/resolve?path=` survives that and is the reason it can: it turns a name
path into an id **once**, so `<slug>/reference/face/<file>` keeps working as an
*address* on a command line while ceasing to be a key anywhere.

## Three rules hold across every route in this file

**`blob_key` never leaves.** `support.view` is an allowlist, not a `pop` — a
denylist would leak the next internal attribute anybody adds, on the day it was
added rather than on the day somebody noticed. Hand a client a blob key and
somebody will split it on `/`, and the coupling the catalog was built to remove
comes straight back.

**Every response is membership-checked against the node's own `lib`**, never
against the library the request asserted. A node id is a v4 UUID, so this is not
a guard against enumeration; it is the guard against a *shared* id.

**A missing node is 404 before the membership check can run**, because the record
is what names the library. An id nobody was given cannot be guessed, so the
difference between "no such node" and "not yours" is unreachable anyway.

## The one refusal that is new

**A folder that is some entity's root cannot be deleted while the entity
exists.** `services.layout` explains why that is the *only* structural rule left:
every other folder in a character or a project may be renamed, moved or deleted
freely, because reference-ness and run-ness are row attributes rather than
locations. The root is different only because a record names it.

## What comes from `before_request` (#351)

`g.caller_sub` and `g.library` are set on every request before any route here
runs, so nothing in this file verifies a token or reads a header to decide which
library a request is about. `/api/resolve` — the one route with no node to take a
library from — reads `g.library`, which is the hook's three cases already
resolved.
"""

import logging

from flask import Blueprint, g, jsonify, request

from studio_core import config
from studio_core.clients.aws import s3
from studio_core.errors import NotFoundError, ValidationError
from studio_core.routes import support
from studio_core.services import browse, catalog, manage

logger = logging.getLogger(__name__)

bp = Blueprint("nodes", __name__, url_prefix="/api")


@bp.get("/nodes")
def list_nodes():
    """The children of one folder, name-ascending, each with its owner.

    **One query, a batched read, and one owner resolution for the whole
    listing.** `catalog.children` reads the by-parent items, whose projection is
    `node_id, lib, kind, path, created_at` — no `size`, no `content_type` — so
    the records come from `catalog.records`, which is `ceil(n / 100)` more round
    trips. Widening the projection instead would make this one query and put a
    mutable copy of every file's metadata on a second item, which every rename
    and every text edit would then have to keep in step (#309).

    **`owner` is resolved once, from the parent**, and that is what keeps it
    affordable. Every child of one folder sits in the same entity as the folder
    does — the only exception is a child that is an entity root *itself*, and
    such a child carries `entity` and answers for itself. Deriving it per row
    would be a batched read of the same ancestry per thumbnail.

    A bare array, like `/api/libraries`, and folders and files interleaved rather
    than split: `kind` already distinguishes them.
    """
    parent_id = request.args.get("parent")
    if not parent_id:
        raise ValidationError("parent is required")

    held = support.memberships()
    # Read before the listing rather than after, because the parent is what names
    # the library: an empty folder's children carry no `lib` to check, so a
    # listing authorised from its own results would authorise nothing at all for
    # exactly the folders that have nothing in them.
    parent = support.node_at(parent_id, held)
    owner = catalog.owner_of(parent)

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
        views.append(support.view(record, _child_owner(record, owner)))
    return jsonify(views), 200


def _child_owner(record: dict, parent_owner: dict | None) -> dict | None:
    """A child's owner, which is its parent's unless the child is an entity root."""
    if record.get("entity"):
        return catalog.entity_summary(record["entity"])
    return parent_owner


@bp.get("/nodes/<node_id>")
def get_node(node_id: str):
    """One node's record, by id, with the entity it belongs to."""
    held = support.memberships()
    record = support.node_at(node_id, held)
    return jsonify(support.view(record, catalog.owner_of(record))), 200


@bp.get("/nodes/<node_id>/owner")
def node_owner(node_id: str):
    """Which entity a node belongs to, derived from its ancestry.

    **Derived, never stored on the node**, which is what makes it correct after a
    move: the answer changes the moment the file does, without a rewrite of
    anything. A node under the library root belongs to nobody in particular and
    answers `null` — that is a real answer, and it is what folders somebody made
    by hand are supposed to be.

    Its own route rather than only a field on the node view because the SPA asks
    it for a *file it is already showing* — "in <project>", with a link — and a
    second full record for that is a wasted round trip in the other direction.
    """
    held = support.memberships()
    record = support.node_at(node_id, held)
    return jsonify({"id": node_id, "owner": catalog.owner_of(record)}), 200


@bp.get("/resolve")
def resolve():
    """A slash-joined name path to the node it names, walked from the library root.

    **This is the one thing that keeps a person's spelling of a location
    working.** Every command the pipeline runs names a subject and a project
    rather than an id, and every `SKILL.md` is written that way; they ask here
    and get an id. The string is an *address* and never a key — the S3 object
    behind whatever comes back is `characters/<char_id>/<node_id>.<ext>`, which
    nothing outside `services.catalog` ever sees.

    **Splitting on `/` is unambiguous by construction rather than by
    convention.** `keys.clean_name` refuses a slash in a name, so no stored name
    can contain a separator and no escaping is needed on either side.

    **An absent or empty path is the library root**, which is the one node a
    client cannot otherwise reach: `/api/libraries` deliberately returns id, name
    and role and not the root node.

    No membership check on the result, because there is nothing left to check:
    the walk starts at a library resolved from the caller's own memberships, and
    every step is a child of the step before it.
    """
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
            # segment was the first one missing rather than only naming it.
            raise NotFoundError("/".join(walked)) from error

    record = catalog.node(node_id)
    return jsonify(support.view(record, catalog.owner_of(record))), 200


@bp.post("/nodes")
def create_node():
    """Create a folder, or a file whose bytes are about to be uploaded.

    **The parent is what authorises this**, not the library the request resolved:
    the node being created has no `lib` yet, and the parent's is the one it will
    inherit — `catalog.create_node` reads it off the parent rather than taking it
    as an argument, so a node cannot be listed in one library's subtree and owned
    by another.

    **The blob key is stamped here and never again.** It is
    `<owner_kind>/<owner_id>/<node_id>.<ext>`, built from the entity the parent
    resolves to, and after this it is a pointer nothing splits or recomputes.

    **`on_conflict` is `fail` unless a caller asks otherwise, and that default is
    the point of having the field at all.** A taken name is a 409 for the CLI and
    for every existing caller. `number` is the uploader's: a person dragging
    `clip.mp4` into a folder that already holds one means "put this here too", and
    refusing it would make uploading a phone camera roll an exercise in renaming.

    **The response carries the name that was actually taken**, which is how a
    numbering caller learns it landed as `clip (2).mp4`.
    """
    body = support.body()
    parent_id = body.get("parent")
    if not parent_id:
        raise ValidationError("parent is required")

    on_conflict = body.get("on_conflict") or "fail"
    if on_conflict not in ("fail", "number"):
        raise ValidationError("on_conflict must be 'fail' or 'number'")

    held = support.memberships()
    parent = support.node_at(parent_id, held)

    if on_conflict == "number":
        # No `blob_key`, `size` or `content_type` here, and that is not an
        # omission to fill in later. Numbering exists for the upload, which mints
        # a placeholder and learns all three from `HeadObject` at
        # `confirm-upload`; a caller that already knows where its bytes are knows
        # whether the name is free, and gets the 409 it should.
        record = catalog.create_numbered(parent_id, body.get("name"), body.get("kind"))
    else:
        record = catalog.create_node(
            parent_id,
            body.get("name"),
            body.get("kind"),
            blob_key=body.get("blob_key"),
            size=body.get("size"),
            content_type=body.get("content_type"),
        )
    return jsonify(support.view(record, catalog.owner_of(parent))), 201


@bp.patch("/nodes/<node_id>")
def update_node(node_id: str):
    """Rename (`name`), move (`parent`), or describe (`description` / `tags`).

    **Three operations on one address, and exactly one per request.**
    `description` and `tags` count as a single one — they are both metadata about
    what the file shows, a client editing a caption usually sends both, and
    neither can reorder against the other. Mixing a describe with a rename or a
    move is refused for the same reason the first two are refused together.

    **Sending name and parent together is a 400 rather than a guess**, and
    refusing is the point: a request that asks for both has two plausible
    orderings with different outcomes when the destination already holds that
    name, and picking one silently is how a file ends up somewhere nobody looked.

    A name collision is a transaction condition failure and comes back **409**,
    which is what tells the UI to keep the rename field open rather than closing
    it and reporting success.

    **Renaming an entity's root folder here does not rename the entity.** The
    folder is a display name and the entity's slug is a claim; changing the slug
    is `PATCH /api/characters/<id>`, which renames both in one transaction. This
    route is deliberately not made to refuse the divergence — somebody may want a
    folder called something else — but it is the reason the entity route exists.
    """
    body = support.body()
    name = body.get("name")
    parent_id = body.get("parent")
    describing = "description" in body or "tags" in body
    asked = [
        given
        for given in (name is not None, parent_id is not None, describing)
        if given
    ]
    if len(asked) > 1:
        raise ValidationError("send name, or parent, or description/tags — one of the three")
    if not asked:
        raise ValidationError(
            "send name to rename, parent to move, or description/tags to describe"
        )

    held = support.memberships()
    # Read for the membership check and nothing else — `catalog.rename_node` and
    # `catalog.move_node` both re-read the record they are about, and a copy held
    # here would be the stale one.
    support.node_at(node_id, held)

    if describing:
        # **A folder may be described too.** Nothing needs it today and nothing
        # refuses it either: a rule that only files carry prose would be one more
        # thing to state, and "the turnaround angle images" is a reasonable
        # sentence to write on a folder.
        return jsonify(
            support.view(
                catalog.describe_node(
                    node_id,
                    description=body.get("description", ...),
                    tags=body.get("tags", ...),
                )
            )
        ), 200

    if name is not None:
        return jsonify(support.view(catalog.rename_node(node_id, name))), 200

    # **The destination is not re-checked here**, and that is deliberate rather
    # than an omission. `catalog.move_node` already refuses a destination in a
    # different library, so a destination that survives it is in the same one as
    # the node — which was membership-checked above. Repeating the rule here
    # would be a second description of it, and the one that drifts.
    return jsonify(support.view(catalog.move_node(node_id, parent_id))), 200


def _selection(held: dict[str, str]) -> tuple[list[dict], dict]:
    """The `{ids, destination}` body both bulk verbs take, resolved and checked.

    **Everything is resolved before anything is written.** A request naming one
    bad id does nothing at all rather than moving the good ones first and then
    failing — the same ordering `manage.move_nodes` then repeats for the name
    collisions it can see, and for the same reason.
    """
    body = support.body()
    ids = manage.bulk(body.get("ids"), "move")
    destination_id = body.get("destination")
    if not destination_id:
        raise ValidationError("destination is required")

    destination = support.node_at(destination_id, held)
    return [support.node_at(node_id, held) for node_id in ids], destination


@bp.post("/nodes/move")
def move_nodes():
    """Move files and folders into another folder. One route for both kinds."""
    held = support.memberships()
    records, destination = _selection(held)
    return jsonify(manage.move_nodes(records, destination)), 200


@bp.post("/nodes/copy")
def copy_nodes():
    """Copy files into another folder, leaving the sources alone.

    201 rather than 200 because something new exists afterwards, which is the one
    thing that distinguishes it from the move beside it. The copies' bytes are
    filed under the **destination's** owner, so a run output copied into a
    character's reference pool becomes the character's.
    """
    held = support.memberships()
    records, destination = _selection(held)
    owner = catalog.owner_of(destination)

    result = manage.copy_nodes(records, destination)
    # The service hands back full records because it is the thing that wrote
    # them; the allowlist is applied here, once, so `blob_key` does not leave on
    # the one response that has a freshly minted one for every entry.
    result["nodes"] = [support.view(record, owner) for record in result["nodes"]]
    return jsonify(result), 201


@bp.delete("/nodes")
def delete_nodes():
    """Delete files and folders, by id, in bulk.

    A body on a DELETE, which is unusual but well-defined and passed through
    intact by API Gateway's Lambda proxy integration. The alternative — repeated
    `?id=` parameters — runs into URL length limits on exactly the case this
    exists for, which is a grid selection of a few hundred files.
    """
    held = support.memberships()
    ids = manage.bulk(support.body().get("ids"), "delete")
    records = [support.node_at(node_id, held) for node_id in ids]
    manage.drain(g.library)
    return jsonify(manage.delete_nodes(records)), 200


@bp.delete("/nodes/<node_id>")
def delete_node(node_id: str):
    """Delete one node and everything beneath it, rows first and then blobs.

    Kept beside the bulk verb rather than folded into it because a single delete
    is a REST-shaped request the smoke suite and every share-link client already
    make, and because the two report different things — this one reports how many
    *nodes* went, which for a folder is the subtree.

    **That order is the recoverable one.** A row pointing at a blob that is gone
    is a broken tile in the grid, which is the failure a user sees; the reverse
    leaves an object no reader can reach, and `catalog.delete_node` opens a sweep
    naming it before the rows go so it stays addressable rather than having to be
    found by scanning.
    """
    held = support.memberships()
    # The authorisation, and the 404 for an id naming nothing. `delete_node` reads
    # the record it is about, so nothing is kept from this call.
    support.node_at(node_id, held)

    manage.drain(g.library)
    result = catalog.delete_node(node_id)
    manage.release(result["lib"], result["blob_keys"], result["sweep"])
    # `blob_keys` is not returned. It is the internal half of a record for the
    # reason `support.view` exists, and a client that received one would
    # eventually parse it.
    return jsonify({"id": result["node_id"], "deleted": result["deleted"]}), 200


@bp.get("/nodes/<node_id>/text")
def read_text(node_id: str):
    """A JSON/markdown/text node's contents, for the viewer and its editor.

    Paired with the `PATCH` below on one address, which is the whole of what this
    replaces: `GET /api/text?key=` read an S3 key and `PATCH /api/text?key=`
    walked a name path, so the two agreed only for material written before the
    catalog — a file the editor could save was a file the editor could not
    re-open.
    """
    held = support.memberships()
    record = support.node_at(node_id, held)
    return jsonify(browse.text_object(record)), 200


@bp.patch("/nodes/<node_id>/text")
def write_text(node_id: str):
    """Overwrite a text node's contents.

    PATCH rather than PUT, and it is worth knowing this is a CORS decision rather
    than a REST one: the browser's preflight is answered by API Gateway's MOCK
    integration and not by Flask, so a verb this service starts accepting has to
    be added in four places at once or it fails as an opaque CORS error with no
    status at all.
    """
    held = support.memberships()
    record = support.node_at(node_id, held)
    return jsonify(manage.update_text(record, support.body().get("content"))), 200


@bp.post("/nodes/<node_id>/transfer")
def transfer_node(node_id: str):
    """Hand a subtree to another library. Owner in both, or 403.

    **Its own route rather than a `parent` in the patch above**, because
    `catalog.move_node` refuses a destination in another library on purpose and
    that refusal is worth keeping: a transfer changes who can reach the branch,
    and the check that makes it safe is one a move has no reason to make.

    **Two libraries, two checks, and which is which is the point of writing them
    on separate lines.** The first is against the node's own `lib` — read off the
    record, never off `g.library`. The second is against the library named in the
    body. The caller needs `owner` in both: in the source because the subtree is
    leaving it, and in the destination because everyone there is about to be able
    to read it.

    **The node keeps its id, so every share link to it survives** — and now
    resolves only for members of the destination.
    """
    body = support.body()
    lib = body.get("lib")
    if not isinstance(lib, str) or not lib:
        raise ValidationError("lib is required")

    held = support.memberships()
    record = catalog.node(node_id)
    support.owner_of(record["lib"], held)  # the source: the node's own library
    support.owner_of(lib, held)  # the destination: the library the body names

    # 200 and not 201: nothing new exists, and the response is the node it has
    # always been with a different `lib`.
    return jsonify(support.view(catalog.transfer_node(node_id, lib))), 200


@bp.get("/nodes/<node_id>/download-url")
def download_url(node_id: str):
    """A fresh presigned GET for one node's blob.

    **Signed fresh on every call rather than returned by the listing routes.** A
    presigned URL dies with the credentials that signed it, not with the
    `ExpiresIn` it was asked for: the Lambda's role credentials rotate, and a URL
    outlives them by nothing.

    `disposition=attachment` is what makes a download download. The URL points at
    S3, so it is cross-origin to the app, and a cross-origin `<a download>` is
    ignored by browsers — signing `response-content-disposition` into the URL is
    the only thing that works. The filename comes from the node's `name`, which is
    the one a person recognises; `blob_key` carries an entity id and a node id and
    would mean nothing to them.

    A folder has no blob and is a **400** rather than a 404: the node is there,
    the request does not apply to it.
    """
    held = support.memberships()
    record = support.node_at(node_id, held)

    blob_key = record.get("blob_key")
    if not blob_key:
        raise ValidationError("a folder has nothing to download")

    disposition = request.args.get("disposition") or "inline"
    if disposition not in ("inline", "attachment"):
        raise ValidationError("disposition must be 'inline' or 'attachment'")

    # `head` before signing, so a record pointing at a blob that is not there is a
    # clean 404 here rather than a URL that only fails once the browser follows
    # it.
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

    **The bytes never transit the Lambda**, which is what makes this possible at
    all: an upload through the API would blow the 6 MB request limit on any
    video. It also means the API never sees what is stored.

    **The grant is one object, one length, one type, once.** `content-length` and
    `content-type` are signed headers, so a client sending different values fails
    signature validation and writes nothing. The key is signed too, so a URL
    issued for this node cannot be redirected at another object. The TTL is
    `config.upload_ttl_seconds`, shorter than a read URL's and well under the
    Lambda credential lifetime.

    **Still no multipart grant.** `max_upload_bytes` is S3's single-PUT ceiling
    rather than a policy number.

    The row is not touched here. The node stays a placeholder — a key with no
    object behind it — until `confirm-upload` runs.
    """
    body = support.body()
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

    held = support.memberships()
    record = support.node_at(node_id, held)
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
    than from anything the client says. The client already declared a size when it
    asked for the URL; repeating it here would trust the same claim twice instead
    of checking it once. S3 knows what it stored.

    Until this runs the node is a placeholder, and `browse.is_abandoned_upload`
    keeps it out of a listing — a row naming a key with nothing behind it draws a
    tile that will not load, which is the state #442 reported.
    """
    held = support.memberships()
    record = support.node_at(node_id, held)
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
    return jsonify(support.view(updated)), 200


def _api_blob_key(record: dict) -> str:
    """The key both upload routes work on, or a refusal.

    Shared so the two cannot disagree about which objects are writable through a
    signature — a distinction a signed URL makes permanent the moment it is
    handed out.

    **The recorded key is used, never a re-derived one**, which is the rule the
    entity model made load-bearing: the key carries the owner the node had when
    it was created, and a node that has since moved between owners would
    otherwise be signed for a key nothing is stored at. `catalog.is_api_blob`
    checks the *tail* — `<node_id>.<ext>`, which cannot change — so a node whose
    bytes predate the catalog is still refused.
    """
    if record["kind"] != catalog.KIND_FILE:
        raise ValidationError("only a file can carry a blob")
    if not catalog.is_api_blob(record):
        raise ValidationError("this node's blob was not written through the API")
    return record["blob_key"]
