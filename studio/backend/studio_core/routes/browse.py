"""What is left of the rendering read surface: one node's bytes, and health.

**The listings moved to `GET /api/nodes`.** `GET /api/tree` and `GET /api/reel`
were two of the three answers this API gave to "what is under this node" — the
third being `GET /api/nodes?parent=`, which the pipeline used — and they were
split by which client asked rather than by what was being asked. Depth, kind and
paging are arguments now, so there is one listing and `services/browse.entries`
is it. The names went with the endpoints: `reel` described how the SPA drew a
result, which is not a thing a route should be named after.

**Every route here takes `?node=<id>` and nothing else.** `?prefix=` is gone,
and so is the raw S3 key `/api/asset` used to accept. The name path survived
this long because share links were made of names and because the pipeline's
shared material — the phrasebook, the angle images — had no node to be addressed
by. Ids in URLs everywhere answered the first; making the phrasebook rows and
the angle images nodes answered the second. One addressing scheme, no exceptions.

`GET /api/text` is not here any more either: reading a text file is
`GET /api/nodes/<id>/text`, paired with the `PATCH` beside it, so the two
directions of one operation sit on one address.
"""

from flask import Blueprint, jsonify, request

from studio_core.routes import support
from studio_core.services import browse

bp = Blueprint("browse", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


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
