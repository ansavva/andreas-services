"""The rendering read surface: a folder ready to draw, and the reel over it.

Distinct from `routes/nodes.py`, which is the catalog's *record* surface. Both
read the same rows; the difference is what they hand back. `GET /api/nodes`
returns bare records — no URLs, no sort, no breadcrumbs, no counts — because it
answers "what is this node". These answer "draw this folder", which needs all
four.

**Every route here takes `?node=<id>` and nothing else.** `?prefix=` is gone,
and so is the raw S3 key `/api/asset` used to accept. The name path survived
this long because share links were made of names and because the pipeline's
shared material — the phrasebook, the pose plates — had no node to be addressed
by. Ids in URLs everywhere answered the first; making the phrasebook rows and
the plates nodes answered the second. One addressing scheme, no exceptions.

`GET /api/text` is not here any more either: reading a text file is
`GET /api/nodes/<id>/text`, paired with the `PATCH` beside it, so the two
directions of one operation sit on one address.
"""

from flask import Blueprint, g, jsonify, request

from studio_core.routes import support
from studio_core.services import browse

bp = Blueprint("browse", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@bp.get("/tree")
def tree():
    """Immediate contents of one folder."""
    return jsonify(
        browse.list_folder(g.library, request.args.get("node"), request.args.get("sort"))
    ), 200


@bp.get("/reel")
def reel():
    """Images and videos beneath a folder, recursively and paginated."""
    return jsonify(
        browse.reel_items(
            g.library,
            request.args.get("node"),
            request.args.get("cursor"),
            request.args.get("page_size"),
            request.args.get("sort"),
        )
    ), 200


@bp.get("/asset")
def asset():
    """A fresh presigned URL for one node's bytes — refreshes and downloads.

    Kept beside `GET /api/nodes/<id>/download-url` rather than merged into it,
    because the two answer different questions with the same signature: this one
    reports what a *listing* reports (`key`, `kind`, `language`-adjacent fields)
    for a viewer that already has the row, and that one reports a download. The
    merge is owed and is not free — the SPA calls this one on every expired tile.
    """
    held = support.memberships()
    record = support.node_at(request.args.get("node"), held)
    return jsonify(browse.asset_url(record, request.args.get("disposition"))), 200
