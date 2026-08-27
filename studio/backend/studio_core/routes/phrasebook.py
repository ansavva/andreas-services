"""The phrasebook: a per-model list of avoid/use pairs, finally a table.

It was `phrasebook/wording.yaml` — one document at the top of the bucket,
belonging to no character and no project, with no catalog node. That is not a
small detail: it was the **sole reason** `GET /api/asset?key=` still took a raw
S3 key, and therefore the reason `keys.clean_key` and the traversal rules under
it were still alive. Making it rows retired all of it.

`LIB#<lib>` / `TERM#<model>#<avoid>`. The model comes first in the sort key even
though the *pair* is what makes a term unique, because reading one model's list
is the common request and `begins_with` is cheaper than a filter.

`phrasebook add` can no longer fail on a library that has never held the
document, because there is no document — a first term is just a first row.
"""

import logging

from flask import Blueprint, g, jsonify, request

from studio_core.errors import ConflictError, ValidationError
from studio_core.routes import support
from studio_core.services import catalog

logger = logging.getLogger(__name__)

bp = Blueprint("phrasebook", __name__, url_prefix="/api")


@bp.get("/phrasebook")
def list_terms():
    """The wording list, optionally for one model."""
    held = support.memberships()
    support.member_of(g.library, held)
    return jsonify({"terms": catalog.terms(g.library, request.args.get("model"))}), 200


@bp.post("/phrasebook")
def add_term():
    """Claim one avoid/use pair. A duplicate is a 409, not an overwrite.

    Conditional, for the reason every claim in this service is: the pair *is* the
    key, so "already there" is a condition failure rather than a read somebody
    raced.
    """
    body = support.body()
    held = support.memberships()
    support.member_of(g.library, held)

    model = body.get("model")
    avoid = body.get("avoid")
    use = body.get("use")
    for name, value in (("model", model), ("avoid", avoid), ("use", use)):
        if not isinstance(value, str) or not value:
            raise ValidationError(f"{name} is required")
    if "#" in model or "#" in avoid:
        # `#` is the key separator. Refused rather than escaped, because a term
        # holding one would be indistinguishable from a different model's term
        # and there is no reason a word needs one.
        raise ValidationError("model and avoid may not contain '#'")

    try:
        record = catalog.add_term(g.library, model, avoid, use, body.get("note"),
                                  body.get("replicate"))
    except ConflictError as conflict:
        return support.structured("conflict", str(conflict), 409)
    return jsonify(record), 201


@bp.delete("/phrasebook/<path:model>/<avoid>")
def delete_term(model: str, avoid: str):
    """Drop one pair.

    `<path:model>` because a model id is `google/nano-banana-pro` — a slash in the
    middle of a path segment, which is exactly what the `path` converter is for.
    Werkzeug matches it greedily and leaves the final segment to `avoid`, so the
    split falls on the last slash, which is where the word begins.
    """
    held = support.memberships()
    support.member_of(g.library, held)
    catalog.delete_term(g.library, model, avoid)
    return jsonify({"model": model, "avoid": avoid, "deleted": True}), 200
