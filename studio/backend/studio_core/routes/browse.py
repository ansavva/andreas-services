"""The rendering read surface: a folder ready to draw, and the reel over it.

Distinct from `routes/nodes.py`, which is the catalog's *record* surface. Both
read the same rows since #309; the difference is what they hand back.
`GET /api/nodes` returns bare records — no URLs, no sort, no breadcrumbs, no
counts — because it answers "what is this node". These two answer "draw this
folder", which needs all four.

**Both accept `?node=<id>` and `?prefix=<path>`, and exactly one of them.** The
id is the cheaper address and the one #313 moves the SPA onto: a listing is a
query on the parent id, so `?node=` is the argument the query already wants,
while `?prefix=` costs a `GetItem` per segment to walk the path down from the
library root first. The path address stays because every share link ever handed
out is one. Sending both is a 400 rather than a guess — `services.browse`
refuses it, for the reason `PATCH /api/nodes/<id>` refuses `name` with `parent`.
"""

from flask import Blueprint, g, jsonify, request

from studio_core.services import browse

bp = Blueprint("browse", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@bp.get("/tree")
def tree():
    """Immediate contents of one folder."""
    return jsonify(
        browse.list_folder(
            g.library,
            request.args.get("prefix"),
            request.args.get("sort"),
            node_id=request.args.get("node"),
        )
    ), 200


@bp.get("/reel")
def reel():
    """Images and videos beneath a folder, recursively and paginated."""
    return jsonify(
        browse.reel_items(
            g.library,
            request.args.get("prefix"),
            request.args.get("cursor"),
            request.args.get("page_size"),
            request.args.get("sort"),
            node_id=request.args.get("node"),
        )
    ), 200


@bp.get("/asset")
def asset():
    """A fresh presigned URL for one object — refreshes and downloads."""
    return jsonify(
        browse.asset_url(request.args.get("key"), request.args.get("disposition"))
    ), 200


@bp.get("/text")
def text():
    """A JSON/markdown/text object's contents, for the read-only viewer."""
    return jsonify(browse.text_object(request.args.get("key"))), 200
