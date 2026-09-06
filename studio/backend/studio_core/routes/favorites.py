"""One person's favorites: the grid, and the heart that fills it.

Three routes, and the shape of them is the model. A favorite is a fact about the
**caller** rather than about the file — see `services/favorites.py` — so the
collection is `/api/favorites` and not a field on `/api/nodes/<id>`: two members
of one library reading the same node are entitled to see different hearts, and
an attribute on the row could not say so.

**`POST` and `DELETE` on the same address, and no toggle.** A toggle needs the
client and the server to agree on the current state before it fires, which two
tabs and one double-tap reliably break. `POST` means favorited and `DELETE`
means not, both are idempotent, and pressing the heart twice from two places
lands on the state the last press asked for rather than on whichever parity won.

**Two views, because there are two questions.** The default is the grid: a page
of hydrated, presigned media, newest pick first. `?view=ids` is the set — every
favorited node id and nothing else — which is what draws a filled heart on a
tile anywhere else in the app, once, instead of a request per tile.
"""

import logging

from flask import Blueprint, g, jsonify, request

from studio_core.errors import ValidationError
from studio_core.routes import support
from studio_core.services import favorites

logger = logging.getLogger(__name__)

bp = Blueprint("favorites", __name__, url_prefix="/api")

VIEWS = ("grid", "ids")


@bp.get("/favorites")
def list_favorites():
    """This caller's favorites in the resolved library, newest pick first."""
    held = support.memberships()
    support.member_of(g.library, held)

    view = request.args.get("view") or "grid"
    if view not in VIEWS:
        raise ValidationError(f"view must be one of {', '.join(VIEWS)}")

    if view == "ids":
        return jsonify({"ids": favorites.ids(g.caller_sub, g.library)}), 200

    return jsonify(
        favorites.listing(
            g.caller_sub,
            g.library,
            cursor=request.args.get("cursor"),
            page_size=request.args.get("limit"),
        )
    ), 200


@bp.post("/favorites/<node_id>")
def add_favorite(node_id: str):
    """Favorite one image or video. Idempotent, and keeps the first press's time.

    `201` on both presses. The second one changed nothing, and a `200` that
    meant "you already had this" would be a distinction the SPA has no use for
    and would have to branch on anyway.
    """
    held = support.memberships()
    record = support.node_at(node_id, held)
    written = favorites.add(g.caller_sub, record)
    return jsonify({"node": node_id, "favorite": True, **written}), 201


@bp.delete("/favorites/<node_id>")
def remove_favorite(node_id: str):
    """Unfavorite one node.

    **Membership-checked like every other route**, against the node's own
    library — a caller may not write into a partition keyed on a library they
    are not in, even to remove something. A node that no longer exists is
    `catalog.node`'s 404, which is the honest answer to "unfavorite this": the
    row it points at is unreachable, and the favorite is already invisible.
    """
    held = support.memberships()
    record = support.node_at(node_id, held)
    favorites.remove(g.caller_sub, record)
    return jsonify({"node": node_id, "favorite": False}), 200
