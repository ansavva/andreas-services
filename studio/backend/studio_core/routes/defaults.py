"""One person's starting params per model: the create sheet's "Set as default".

The registry snapshot says what a model's inputs default to, and the create
sheet seeds a fresh run from it. These routes let a person say "start from
THESE instead" — for one model, for them, wherever they sign in — which is the
same shape as a favorite (`routes/favorites.py`): a fact about the caller,
filed under the caller, and two members of one library are entitled to
different answers.

**Keyed on the Replicate `owner/name`**, whichever spelling the request used —
the registry key, an alias or the id — because that is what the create sheet
keys its params on, and one model with two rows of defaults is the drift the
normalisation exists to prevent. A model the registry does not know is 404:
there is nothing to default.

**The params are not checked against the schema here.** They are what a
person had in the sheet when they pressed the button, and the sheet's rows
are the live schema; what reaches the provider is checked at submit like every
other payload (`services/schema.py`). What IS refused is the wrong shape — a
non-object, a nested value, a key naming an image field — since a saved
default that the sheet cannot draw is a row that exists to confuse.

`POST` and `DELETE`, not `PUT`: `app_factory.py` says why PUT is allowed
nowhere.
"""

import logging

from flask import Blueprint, g, jsonify, request

from studio_core.errors import NotFoundError, ValidationError
from studio_core.services import catalog, registry

logger = logging.getLogger(__name__)

bp = Blueprint("defaults", __name__, url_prefix="/api")

#: A default may hold what a settings row can draw, and nothing else.
SCALARS = (str, int, float, bool)
MAX_KEYS = 64


def _entry(name: str) -> dict:
    entry = registry.find(name) or registry.by_model_id(name)
    if entry is None:
        raise NotFoundError(name)
    return entry


def _clean(entry: dict, body) -> dict:
    """The params a request may save for this model, or a 400 saying why not."""
    if not isinstance(body, dict):
        raise ValidationError("a JSON object is required")
    params = body.get("params")
    if not isinstance(params, dict):
        raise ValidationError("params must be an object")
    if len(params) > MAX_KEYS:
        raise ValidationError(f"params may hold at most {MAX_KEYS} keys")
    images = entry.get("images") or {}
    sends = {
        key
        for key in ("prompt", images.get("refs"), images.get("start"), images.get("end"),
                    (entry.get("clips") or {}).get("source"))
        if isinstance(key, str)
    }
    for key, value in params.items():
        if not isinstance(key, str) or not key:
            raise ValidationError("every param must be named")
        if key in sends:
            raise ValidationError(f"{key} is not a param — the prompt and the images are sent beside them")
        if not isinstance(value, SCALARS):
            raise ValidationError(f"{key} must be a string, a number or a boolean")
    return params


@bp.get("/defaults/models")
def list_model_defaults():
    """Every model this caller has set defaults for, keyed by Replicate id."""
    return jsonify({"defaults": catalog.model_defaults(g.caller_sub)}), 200


@bp.post("/defaults/models/<path:name>")
def set_model_defaults(name: str):
    """Set this caller's defaults for one model — whole, replacing what was there."""
    entry = _entry(name)
    params = _clean(entry, request.get_json(silent=True))
    written = catalog.put_model_defaults(g.caller_sub, entry["model"], params)
    return jsonify(written), 200


@bp.delete("/defaults/models/<path:name>")
def clear_model_defaults(name: str):
    """Back to the model's own defaults. Clearing what was never set is 200 too.

    A JSON body rather than a bare 204, like `DELETE /api/favorites/<id>`: the
    SPA's client parses every answer as JSON, and an empty body there is a
    parse error dressed as a failed request.
    """
    entry = _entry(name)
    catalog.delete_model_defaults(g.caller_sub, entry["model"])
    return jsonify({"model": entry["model"], "cleared": True}), 200
